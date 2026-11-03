import json
import hashlib
import os
import time
from pathlib import Path

import pytest

from upscalers import catalog, games, ini, logread, recipes
from upscalers.catalog import Asset, Build
from upscalers.service import UpscalerError, UpscalerService

APPID = "292030"


def _write(path: Path, data: bytes | str = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


@pytest.fixture
def steam(tmp_path):
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    _write(root / "steamapps/libraryfolders.vdf", '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n}\n' % root)
    _write(root / f"steamapps/appmanifest_{APPID}.acf",
           '"AppState"\n{\n "appid" "%s"\n "name" "Witcher"\n "installdir" "Witcher"\n "StateFlags" "4"\n}\n' % APPID)
    game = root / "steamapps/common/Witcher"
    _write(game / "REDprelauncher.exe", b"MZ" + b"\0" * 64)
    _write(game / "bin/x64_dx12/witcher3.exe", b"MZ" + b"\0" * 4096)
    _write(game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll")
    _write(game / "bin/x64_dx12/nvngx_dlss.dll")
    return home, game


@pytest.fixture
def fake_catalog(monkeypatch, tmp_path):
    def asset(asset_id, filename, content, archive=False):
        return Asset(asset_id, filename, hashlib.sha256(content).hexdigest(), len(content), ("http://invalid",), archive)

    archive = asset(catalog.OPTISCALER_ARCHIVE, "opti.7z", b"archive", archive=True)
    extra = asset("extra", "amdxcffx64.dll", b"provider")
    assets = {a.id: a for a in (archive, extra)}
    builds = {
        "fsr-test": Build("fsr-test", "fsr", "4.1.1", ("rdna2",), 3, 3, assets=("extra",),
                          ini={"FSR.Fsr4Update": "true"}),
        "fsr-later": Build("fsr-later", "fsr", "4.1.2", ("rdna2",), 3, 3, available=False),
    }
    monkeypatch.setattr(catalog, "ASSETS", assets)
    monkeypatch.setattr(catalog, "BUILDS", builds)

    state = tmp_path / "state"
    unpacked = state / "cache" / archive.sha256 / "unpacked"
    _write(unpacked / "OptiScaler.dll", b"injector")
    _write(unpacked / "OptiScaler.ini", "[FSR]\nFsr4Update=auto\n[Log]\nLogToFile=auto\n")
    _write(unpacked / "amd_fidelityfx_upscaler_dx12.dll", b"sdk")
    _write(unpacked / "D3D12_Optiscaler/D3D12Core.dll", b"core")
    _write(unpacked / "setup_linux.sh", b"junk")
    _write(unpacked / ".complete", archive.sha256)
    _write(state / "cache" / extra.sha256 / extra.filename, b"provider")
    return state


def _service(steam, state, proc, search=lambda term: []):
    home, _ = steam
    service = UpscalerService(str(home), str(state), "rdna2", proc=str(proc))
    service.search = search
    return service


@pytest.fixture
def proc(tmp_path):
    path = tmp_path / "proc"
    path.mkdir()
    return path


def test_ini_apply_replaces_adds_and_creates_sections_keeping_crlf():
    text = "; head\r\n[FSR]\r\nFsr4Update=auto\r\n[Log]\r\nLogToFile=auto\r\n"
    out = ini.apply(text, {"FSR.Fsr4Update": "true", "FSR.Fsr4ForceModel": "2", "Plugins.Load": "true"})
    assert "Fsr4Update=true\r\n" in out
    assert out.index("Fsr4ForceModel=2") < out.index("[Log]")
    assert out.endswith("[Plugins]\r\nLoad=true\r\n")
    assert ini.read(out, "FSR.Fsr4ForceModel") == "2"


def test_analyze_prefers_the_game_exe_over_its_launcher(steam, monkeypatch):
    _, game = steam
    monkeypatch.setattr(games.pe, "graphics_apis", lambda path: ["d3d12"] if path.endswith("witcher3.exe") else [])
    result = games.analyze(game)
    assert result["exe"] == "bin/x64_dx12/witcher3.exe"
    assert result["target"] == str(game / "bin/x64_dx12")
    assert set(result["inputs"]) == {"fsr31", "dlss"}
    assert result["anti_cheat"] is False and result["foreign"] is False


def test_manual_exe_wins_and_detects_anti_cheat_and_foreign(steam):
    _, game = steam
    _write(game / "EasyAntiCheat/EasyAntiCheat_EOS_Setup.exe")
    _write(game / "OptiScaler.ini", "x")
    result = games.analyze(game, "REDprelauncher.exe")
    assert result["manual"] is True and result["exe"] == "REDprelauncher.exe"
    assert result["anti_cheat"] is True and result["foreign"] is True


def test_install_backs_up_then_uninstall_restores_exactly(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    _write(target / "dxgi.dll", b"original")
    service = _service(steam, fake_catalog, proc)
    service.begin("install", APPID)

    result = service.install(APPID, {"build": "fsr-test", "quality": "balanced", "sharpness": "soft"})

    assert result["overrides"] == ["dxgi=n,b"]
    assert result["args"] == ["--launcher-skip", "-dx12"]
    assert (target / "dxgi.dll").read_bytes() == b"injector"
    assert (target / "amdxcffx64.dll").read_bytes() == b"provider"
    assert (target / "D3D12_Optiscaler/D3D12Core.dll").is_file()
    assert not (target / "setup_linux.sh").exists()
    text = (target / "OptiScaler.ini").read_text()
    assert ini.read(text, "FSR.Fsr4Update") == "true"
    assert ini.read(text, "Log.LogToFile") == "true"
    assert ini.read(text, "QualityOverrides.QualityRatioQuality") == "1.70"
    assert ini.read(text, "Sharpness.Sharpness") == "0.30"
    assert service.overview()["installs"][APPID]["status"] == "pending"

    _write(target / "OptiScaler.log", "OptiScaler v0.9.4\n")
    assert service.uninstall(APPID)["kept"] == []
    assert (target / "dxgi.dll").read_bytes() == b"original"
    assert sorted(p.name for p in target.iterdir()) == [
        "amd_fidelityfx_upscaler_dx12.dll", "dxgi.dll", "nvngx_dlss.dll", "witcher3.exe",
    ]


def test_uninstall_keeps_files_changed_after_install(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    _write(target / "amdxcffx64.dll", b"user replaced it")
    assert service.uninstall(APPID)["kept"] == ["amdxcffx64.dll"]
    assert (target / "amdxcffx64.dll").read_bytes() == b"user replaced it"


def test_refuses_running_updating_foreign_and_unavailable(steam, fake_catalog, proc):
    home, game = steam
    service = _service(steam, fake_catalog, proc)
    with pytest.raises(UpscalerError, match="unknown_build"):
        service.install(APPID, {"build": "fsr-later"})

    _write(proc / "4242/cmdline", f"Z:{game}/bin/x64_dx12/witcher3.exe".replace("/", "\\"))
    with pytest.raises(UpscalerError, match="running"):
        service.install(APPID, {"build": "fsr-test"})
    (proc / "4242/cmdline").unlink()

    _write(game / "bin/x64_dx12/OptiScaler.ini", "foreign")
    with pytest.raises(UpscalerError, match="foreign"):
        service.install(APPID, {"build": "fsr-test"})

    manifest = home / f".local/share/Steam/steamapps/appmanifest_{APPID}.acf"
    manifest.write_text(manifest.read_text().replace('"StateFlags" "4"', '"StateFlags" "6"'))
    with pytest.raises(UpscalerError, match="update_pending"):
        service.install(APPID, {"build": "fsr-test"})
    manifest.write_text(manifest.read_text().replace('"StateFlags" "6"', '"StateFlags" "1030"'))
    with pytest.raises(UpscalerError, match="updating"):
        service.install(APPID, {"build": "fsr-test"})


def test_verify_reads_the_log_written_after_install(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    assert service.verify(APPID)["result"] == "not_run"

    log = _write(target / "OptiScaler.log", "[12:00:00.000] [I] OptiScaler v0.9.4\n"
                 "[12:00:01.000] [I] Creating new FSR 3.X/4 upscaler\n")
    future = time.time() + 5
    os.utime(log, (future, future))
    verdict = service.verify(APPID)
    assert verdict["result"] == "active"
    assert verdict["facts"]["upscaler"] == "FSR 3.X/4"
    history = service.game(APPID)["history"]
    assert history[-1]["result"] == "active"


def test_broken_when_a_game_update_removes_the_proxy(steam, fake_catalog, proc):
    _, game = steam
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    (game / "bin/x64_dx12/dxgi.dll").unlink()
    assert service.overview()["installs"][APPID]["status"] == "broken"


def test_catalog_hashes_are_well_formed_and_every_build_resolves():
    for asset in catalog.ASSETS.values():
        assert len(asset.sha256) == 64 and asset.urls
    for build in catalog.BUILDS.values():
        if build.available:
            assert catalog.build_assets(build)[0].id == build.archive and catalog.ASSETS[build.archive].archive
    assert catalog.preferred_build("rdna2") == "fsr-4.1.1-rdna2"
    assert logread.verdict({"present": False}) == "not_run"


def test_panel_resolution_prefers_the_internal_panel(tmp_path):
    from upscalers.service import panel_resolution
    for name, status, mode in (("card0-DP-1", "connected", "3840x2160"), ("card0-eDP-1", "connected", "1920x1200"),
                               ("card0-HDMI-A-1", "disconnected", "")):
        _write(tmp_path / name / "status", status + "\n")
        _write(tmp_path / name / "modes", mode + "\n")
    assert panel_resolution(str(tmp_path)) == [1920, 1200]
    assert panel_resolution(str(tmp_path / "missing")) is None


def test_compatibility_flags_games_that_ship_an_upscaler(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    assert service.compatibility([APPID, "999"]) == {APPID: True}


def test_log_reader_takes_real_optiscaler_lines(tmp_path):
    log = _write(tmp_path / "OptiScaler.log",
                 "[13:19:00.245658] [W] OptiScaler v0.9.4-final (7534ad0) loaded\n"
                 "[13:19:00.252768] [I] CheckWorkingMode OptiScaler working as dxgi.dll, system dll loaded\n"
                 "[13:19:07.990345] [E] hkD3D12CreateDevice ppDevice is nullptr\n"
                 "[13:21:05.132712] [I] CreateDLSSContext renderWidth: 936, maxWidth: 1440, ratio: 1.5384616\n"
                 "[13:21:05.132848] [I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\n"
                 "[13:21:05.132956] [I] IFeature::SetInitParameters Render Resolution: 936x624, Display Resolution 1440x960, Quality: 1\n")
    facts = logread.read(log.parent)
    assert facts["version"] == "0.9.4-final"
    assert facts["proxy"] == "dxgi.dll"
    assert facts["upscaler"] == "fsr31"
    assert facts["input"] == "DLSS"
    assert facts["resolution"] == {"render": [936, 624], "output": [1440, 960]}
    assert facts["errors"] == 1
    assert logread.verdict(facts) == "active"


def test_recipe_adds_files_dlls_and_args_then_undoes_them(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    target = game / "bin/x64_dx12"
    content = b"ref"
    member = Asset("ref", "REF.zip", hashlib.sha256(b"zip").hexdigest(), 3, ("http://invalid",), member="dinput8.dll")
    monkeypatch.setitem(catalog.ASSETS, "ref", member)
    _write(fake_catalog / "cache" / member.sha256 / "unpacked" / "dinput8.dll", content)
    monkeypatch.setattr(recipes, "RECIPES", {APPID: recipes.Recipe(
        APPID, exe="bin/x64_dx12/witcher3.exe", args=("--launcher-skip",),
        files={"dinput8.dll": "ref"}, native_dlls=("dinput8",))})
    service = _service(steam, fake_catalog, proc)

    result = service.install(APPID, {"build": "fsr-test"})
    assert result["overrides"] == ["dxgi=n,b", "dinput8=n,b"]
    assert result["args"] == ["--launcher-skip"]
    assert (target / "dinput8.dll").read_bytes() == content
    assert service.game(APPID)["recipe"] is True

    service.record_added_args(APPID, ["--launcher-skip", "-unknown"])
    removed = service.uninstall(APPID)
    assert removed["args"] == ["--launcher-skip"]
    assert removed["overrides"] == ["dxgi=n,b", "dinput8=n,b"]
    assert not (target / "dinput8.dll").exists()


def test_capture_moves_gamescope_shot_and_keeps_a_few(tmp_path):
    from upscalers import capture

    def fake_run(verb, path):
        Path(path).write_bytes(b"\x89PNG fake")
        return 0, ""

    folder = tmp_path / "compare"
    for index in range(capture.KEEP + 2):
        shot = capture.take(folder, f"s{index}", run=fake_run, scratch=str(tmp_path))
        os.utime(shot, (index, index))
    assert len(list(folder.glob("*.png"))) == capture.KEEP
    assert capture.data_url(shot).startswith("data:image/png;base64,")

    with pytest.raises(capture.CaptureError):
        capture.take(folder, "bad", run=lambda *a: (1, ""), scratch=str(tmp_path))


def test_report_explains_an_install_from_the_bundle_alone(steam, fake_catalog, proc):
    home, game = steam
    root = home / ".local/share/Steam"
    _write(root / "config/config.vdf",
           '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "%s" { "name" "proton_experimental" } } } } } }' % APPID)
    _write(root / "userdata/123/config/localconfig.vdf",
           '"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "%s" { "LaunchOptions" "WINEDLLOVERRIDES=\\"dxgi=n,b\\" %%command%%" } } } } } }' % APPID)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    target = game / "bin/x64_dx12"
    log = _write(target / "OptiScaler.log", "[W] OptiScaler v0.9.4 loaded\n[I] VulkanSpoofing noise\n[E] hkD3D12CreateDevice ppDevice is nullptr\n")
    future = time.time() + 5
    os.utime(log, (future, future))
    (target / "amdxcffx64.dll").write_bytes(b"tampered")

    report = service.report()
    game_report = report["games"][0]
    assert game_report["steam"] == {"compat_tool": "proton_experimental", "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" %command%'}
    assert game_report["manifest"]["changed"] == ["amdxcffx64.dll"]
    assert game_report["ini"]["FSR.Fsr4Update"] == "true"
    assert game_report["log_verdict"] == "loaded"
    assert any("ppDevice" in line for line in game_report["log_excerpt"])
    assert not any("VulkanSpoofing" in line for line in game_report["log_excerpt"])
    assert "kernel" in report["environment"]


def _shortcuts_vdf(entries: list[dict]) -> bytes:
    def string(key, value):
        return b"\x01" + key.encode() + b"\0" + value.encode() + b"\0"

    def number(key, value):
        return b"\x02" + key.encode() + b"\0" + int(value).to_bytes(4, "little")

    body = b""
    for index, entry in enumerate(entries):
        fields = number("appid", entry["appid"]) + string("AppName", entry["name"]) \
            + string("Exe", entry["exe"]) + string("StartDir", entry["start"])
        body += b"\x00" + str(index).encode() + b"\0" + fields + b"\x08"
    return b"\x00shortcuts\0" + body + b"\x08\x08"


def test_non_steam_shortcut_installs_like_any_game(steam, fake_catalog, proc):
    home, _ = steam
    folder = home / "Games/Cracked Game"
    exe = _write(folder / "bin/game.exe", b"MZ" + b"\0" * 64)
    shortcut_id = 3123456789
    _write(home / ".local/share/Steam/userdata/123/config/shortcuts.vdf", _shortcuts_vdf([
        {"appid": shortcut_id, "name": "Cracked Game", "exe": f'"{exe}"', "start": f'"{folder}"'},
    ]))
    service = _service(steam, fake_catalog, proc)
    detail = service.game(str(shortcut_id))
    assert detail["shortcut"] is True
    assert detail["name"] == "Cracked Game"
    assert detail["analysis"]["exe"] == "bin/game.exe"
    service.install(str(shortcut_id), {"build": "fsr-test"})
    assert (folder / "bin/dxgi.dll").read_bytes() == b"injector"


def test_clean_name_drops_release_tags():
    from upscalers.identify import clean_name
    assert clean_name("Cyberpunk.2077.v2.13-[FitGirl Repack]") == "Cyberpunk 2077"
    assert clean_name("ELDEN_RING-CODEX (Build 12345)") == "ELDEN RING"


def test_identity_prefers_appid_left_by_the_release(tmp_path):
    from upscalers.identify import identify
    root = tmp_path / "Game"
    _write(root / "bin/steam_emu.ini", "[Settings]\nAppId=1091500\n")
    exe = _write(root / "bin/game.exe", b"MZ")
    result = identify("Whatever [DODI]", root, exe, search=lambda term: pytest.fail("no search needed"))
    assert result["steam_appid"] == 1091500 and result["source"] == "steam_emu.ini"


def test_identity_falls_back_to_store_search_on_the_clean_name(tmp_path):
    from upscalers.identify import identify
    root = tmp_path / "The.Witcher.3.v4.04-GOG"
    exe = _write(root / "witcher3.exe", b"MZ")
    asked = []

    def search(term):
        asked.append(term)
        return [{"id": 999, "name": "Witcher Fan Kit"}, {"id": 292030, "name": "The Witcher 3: Wild Hunt"}]

    result = identify("The Witcher 3 [FitGirl Repack]", root, exe, search=search)
    assert asked[0] == "The Witcher 3"
    assert result["steam_appid"] == 292030 and result["source"] == "store:shortcut"


def test_shortcut_identity_applies_the_steam_recipe(steam, fake_catalog, proc, monkeypatch):
    home, _ = steam
    folder = home / "Games/W3"
    exe = _write(folder / "bin/x64_dx12/witcher3.exe", b"MZ" + b"\0" * 64)
    _write(folder / "steam_appid.txt", "292030")
    _write(home / ".local/share/Steam/userdata/123/config/shortcuts.vdf", _shortcuts_vdf([
        {"appid": 3000000001, "name": "W3 GOTY", "exe": f'"{exe}"', "start": f'"{folder}"'},
    ]))
    service = _service(steam, fake_catalog, proc)
    detail = service.game("3000000001")
    assert detail["identity"]["steam_appid"] == 292030
    assert detail["recipe"] is True
    result = service.install("3000000001", {"build": "fsr-test"})
    assert result["args"] == ["--launcher-skip", "-dx12"]


def test_shortcut_hint_covers_shortcuts_missing_from_vdf(steam, fake_catalog, proc, tmp_path):
    home, _ = steam
    native = _write(home / "Downloads/Port-x86_64.appimage", b"ELF")
    windows = _write(home / "Games/Other/game.exe", b"MZ" + b"\0" * 64)
    service = _service(steam, fake_catalog, proc)
    linux = service.game("2953644062", {"exe": f'"{native}"', "dir": "", "name": "Bloodborne"})
    assert linux["native"] is True and linux["analysis"]["target"] is None
    with pytest.raises(UpscalerError, match="native_game"):
        service.install("2953644062", {"build": "fsr-test"})
    win = service.game("2000000001", {"exe": f'"{windows}"', "dir": "", "name": "Other"})
    assert win["native"] is False and win["analysis"]["exe"] == "game.exe"
    assert service.compatibility(["1"]) == {}
    assert "1" not in service.state["games"]


def test_fg_routes_follow_the_wiki_ranking_and_each_generation():
    both = {"dlssg": ["a"], "fsrfg": ["b"], "streamline": ["c"]}
    # Off NVIDIA the game's own FSR FG wins: DLSSG needs spoofing the game may refuse.
    assert catalog.fg_plan("rdna3", both, generation=10, streamline=2)["input"] == "fsrfg"
    assert catalog.fg_plan("nvidia", both, generation=10, streamline=2)["input"] == "dlssg"
    sl2 = {"dlssg": ["a"], "streamline": ["c"]}
    v10 = catalog.fg_plan("rdna3", sl2, generation=10, apis=["d3d12"], streamline=2)
    assert (v10["input"], v10["output"], v10["follows_game"], v10["route"]) == ("dlssg", "fsrfg", True, "game")
    assert catalog.fg_overrides(v10, True)["FrameGen.Enabled"] == "auto"
    assert catalog.fg_plan("rdna3", sl2, generation=9, streamline=2)["input"] == "dlssg"
    # 0.9 cannot read DLSSG through Streamline 1; Nukem's bridge can.
    assert catalog.fg_plan("rdna3", sl2, generation=9, streamline=1)["input"] == "nukems"
    sl1_v10 = catalog.fg_plan("rdna3", sl2, generation=10, streamline=1)
    assert sl1_v10["input"] == "dlssg" and catalog.fg_overrides(sl1_v10, True)["FrameGen.Enabled"] == "true"
    assert catalog.fg_plan("rdna3", {"fsrfg": ["b"]})["input"] == "fsrfg"
    assert catalog.fg_plan("rdna3", {"xefg": ["b"]})["route"] == "optiscaler"
    assert catalog.fg_plan("rdna3", {"xefg": ["b"]}, generation=10)["input"] == "xefg"
    assert catalog.fg_plan("intel", {"xefg": ["b"], "fsrfg": ["c"]}, generation=10)["input"] == "xefg"
    assert catalog.fg_plan("rdna3", {"xefg": ["b"], "fsrfg": ["c"]}, generation=10)["input"] == "fsrfg"


def test_optifg_is_a_choice_and_never_offered_without_dx12():
    plan = catalog.fg_plan("rdna3", {"fsrfg": ["b"]}, apis=["d3d12"], route="optiscaler")
    assert plan["input"] == "upscaler" and set(plan["routes"]) == {"game", "optiscaler"}
    assert catalog.fg_overrides(plan, True)["OptiFG.HUDFix"] == "true"
    assert catalog.fg_route_plan(plan, "game")["input"] == "fsrfg"
    assert catalog.fg_plan("intel", {}, apis=["vulkan"]) is None
    vulkan = catalog.fg_plan("intel", {"dlssg": ["a"]}, apis=["vulkan"], streamline=2)
    assert vulkan["output"] == "fsrfg" and list(vulkan["routes"]) == ["game"]
    assert catalog.fg_overrides(None, False)["FrameGen.FGInput"] == "nofg"


def test_optiscaler_files_never_count_as_the_games_generator(tmp_path):
    root = tmp_path / "Game"
    _write(root / "game.exe", b"MZ")
    _write(root / "OptiScaler/amd_fidelityfx_framegeneration_dx12.dll", b"v10 bundle")
    _write(root / "libxess_fg.dll", b"ours")
    _write(root / "amd_fidelityfx_upscaler_dx12.dll", b"ours, game had one")
    _write(root / games.MANIFEST_DIR / "manifest.json", json.dumps({
        "files": {"libxess_fg.dll": "", "amd_fidelityfx_upscaler_dx12.dll": ""},
        "backups": ["amd_fidelityfx_upscaler_dx12.dll"]}))
    inputs = games.analyze(root)["inputs"]
    assert "fsrfg" not in inputs and "xefg" not in inputs
    assert inputs["fsr31"] == ["amd_fidelityfx_upscaler_dx12.dll"]


def test_frame_generation_is_written_on_install_and_toggled_after(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, fake_catalog, proc)
    _write(target / "amd_fidelityfx_framegeneration_dx12.dll", b"game fg")
    assert service.game(APPID)["fg_plan"]["input"] == "fsrfg"
    service.install(APPID, {"build": "fsr-test", "fg": "on"})
    text = (target / "OptiScaler.ini").read_text()
    assert ini.read(text, "FrameGen.Enabled") == "true"
    assert ini.read(text, "FrameGen.FGInput") == "fsrfg"
    service._game_state(APPID)["install"]["fg_plan"] = {"input": "nukems", "output": "nukems", "source": "game", "experimental": False}
    service.configure(APPID, {"fg": "on", "fg_route": "game"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FrameGen.FGInput") == "fsrfg"
    service.configure(APPID, {"fg": "on", "fg_route": "optiscaler"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FrameGen.FGInput") == "upscaler"
    service.configure(APPID, {"fg": "off"})
    text = (target / "OptiScaler.ini").read_text()
    assert ini.read(text, "FrameGen.Enabled") == "false"
    assert ini.read(text, "FrameGen.FGOutput") == "nofg"

    log = _write(target / "OptiScaler.log", "[I] FSRFG_Dx12::Activate D3D12_Configure Enabled: true, result: FFX_API_RETURN_OK (0)\n")
    future = time.time() + 5
    os.utime(log, (future, future))
    assert service.live(APPID)["fg"] is True


def test_beta_build_uses_the_v10_subfolder_layout(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    target = game / "bin/x64_dx12"
    beta = Asset(catalog.OPTISCALER_BETA, "opti10.7z", hashlib.sha256(b"v10").hexdigest(), 3, ("http://invalid",), archive=True, generation=10)
    monkeypatch.setitem(catalog.ASSETS, catalog.OPTISCALER_BETA, beta)
    monkeypatch.setitem(catalog.BUILDS, "beta", Build(
        "beta", "fsr", "4.1.2", ("rdna2",), 3, 2, assets=("extra",), archive=catalog.OPTISCALER_BETA,
        channel="beta", extra_dir="OptiScaler", ini={"FSR.Fsr4GpuSupport": "2"},
        models=(("full", {"FSR.Fsr4GpuSupport": "2"}), ("lite", {"FSR.Fsr4GpuSupport": "4"}))))
    unpacked = fake_catalog / "cache" / beta.sha256 / "unpacked"
    _write(unpacked / "OptiScaler.dll", b"v10 injector")
    _write(unpacked / "OptiScaler.ini", "[FSR]\nFsr4GpuSupport=auto\n")
    _write(unpacked / "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", b"ffx 4.1.2")
    _write(unpacked / "OptiScaler/Streamlined_fetcher_windows.bat", b"bat")
    _write(unpacked / "setup_linux.sh", b"junk")
    _write(unpacked / ".complete", beta.sha256)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "beta"})
    assert (target / "dxgi.dll").read_bytes() == b"v10 injector"
    assert (target / "OptiScaler/amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"ffx 4.1.2"
    assert (target / "OptiScaler/amdxcffx64.dll").read_bytes() == b"provider"
    assert not (target / "OptiScaler/Streamlined_fetcher_windows.bat").exists()
    # The game's own FFX dll stays untouched in the exe folder.
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "2"
    service.configure(APPID, {"model": "lite"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "4"
    service.configure(APPID, {"model": "bogus"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "2"
    service.uninstall(APPID)
    assert not (target / "OptiScaler").exists()


def test_log_reader_understands_optiscaler_10(tmp_path):
    log = _write(tmp_path / "OptiScaler.log",
                 "[00:05:24.702753] [W] OptiScaler v10.0.0-dev (ab379b25) (20261102_120120) loaded\n"
                 "[00:06:04.046244] [I] TryCreateOptiFeature Creating FSR 3.X upscaler feature\n"
                 "[00:06:04.046456] [I] IFeature::SetInitParameters Render Resolution: 936x624, Display Resolution 1440x960, Quality: 1\n")
    facts = logread.read(log.parent)
    assert facts["version"] == "10.0.0-dev"
    assert facts["upscaler"] == "FSR 3.X"
    assert logread.verdict(facts) == "active"


def test_streamline_version_comes_from_any_version_string(monkeypatch):
    monkeypatch.setattr(games.pe, "version_strings", lambda _: {"OriginalFilename": "SHA: 98614dad6 v2.14.1-rc0"})
    assert games.streamline_major(Path("sl.interposer.dll")) == 2
    monkeypatch.setattr(games.pe, "version_strings", lambda _: {"FileVersion": "1.5.0.0"})
    assert games.streamline_major(Path("sl.interposer.dll")) == 1
    monkeypatch.setattr(games.pe, "version_strings", lambda _: {})
    assert games.streamline_major(Path("sl.interposer.dll")) is None


def test_fsr_inputs_are_not_reported_as_dlss(tmp_path):
    log = _write(tmp_path / "OptiScaler.log",
                 "[I] ffxCreateContext_Dx12 context created: 1EE8\n"
                 "[I] CreateDLSSContext renderWidth: 936, maxWidth: 1440, ratio: 1.5384616\n"
                 "[I] FSRFG_Dx12::Activate D3D12_Configure Enabled: true, result: FFX_API_RETURN_OK (0)\n")
    facts = logread.read(log.parent)
    assert facts["input"] == "FSR3" and facts["fg"]


def test_hotkeys_only_reach_a_running_patched_game(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    pressed = []
    service.press = pressed.append
    with pytest.raises(UpscalerError, match="not_patched"):
        service.press_key(APPID, "menu")
    service.install(APPID, {"build": "fsr-test"})
    with pytest.raises(UpscalerError, match="not_running"):
        service.press_key(APPID, "menu")
    assert pressed == []


def test_virtual_key_press_writes_down_and_up(tmp_path, monkeypatch):
    from upscalers import keys
    calls = []
    monkeypatch.setattr(keys.fcntl, "ioctl", lambda fd, req, *a: calls.append(req))
    device = tmp_path / "uinput"
    device.write_bytes(b"")
    keys.press("fg", str(device), sleep=lambda _: None)
    data = device.read_bytes()
    events = [keys._EVENT.unpack_from(data, len(keys._device_blob()) + i * keys._EVENT.size) for i in range(4)]
    assert [(e[2], e[3], e[4]) for e in events] == [(1, 107, 1), (0, 0, 0), (1, 107, 0), (0, 0, 0)]
    assert calls[-2:] == [keys.UI_DEV_CREATE, keys.UI_DEV_DESTROY]
    with pytest.raises(keys.HotkeyError):
        keys.press("nope", str(device))


def test_optifg_counts_as_running_once_its_context_exists(tmp_path):
    lines = ("[I] FrameGen.FGInput: {}\n"
             "[I] FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0\n")
    log = _write(tmp_path / "OptiScaler.log", lines.format("upscaler"))
    assert logread.read(log.parent)["fg"]
    log.write_text(lines.format("fsrfg"))
    facts = logread.read(log.parent)
    assert "fg" not in facts and "fg_input" not in facts and "fg_context" not in facts


def test_the_last_fg_toggle_wins(tmp_path):
    log = _write(tmp_path / "OptiScaler.log",
                 "[I] FrameGen.FGInput: upscaler\n"
                 "[I] FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0\n"
                 "[I] FSRFG_Dx12::Deactivate D3D12_Configure Enabled: false, result: FFX_API_RETURN_OK (0)\n")
    assert logread.read(log.parent)["fg_state"] == "false"
