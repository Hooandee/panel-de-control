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
    assert ini.read(text, "QualityOverrides.QualityRatioDLAA") == "1.70"
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
        if build.engine == "proton":
            assert catalog.build_assets(build) == []
        elif build.available:
            assert catalog.build_assets(build)[0].id == build.archive
            # HelixSR's ZIP is unpacked into the user's folder by helixsr.HelixSR, not by the cache.
            assert catalog.ASSETS[build.archive].archive == (build.engine != "helixsr")
    assert catalog.preferred_build("rdna2") == "fsr-4.1.2-beta"
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
    assert service.compatibility([APPID, "999"]) == {APPID: {"native": False, "inputs": ["DLSS", "FSR 3.1"]}}


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
        channel="beta", extra_dir="OptiScaler", ini={"FSR.Fsr4GpuSupport": "4"},
        models=(("lite", {"FSR.Fsr4GpuSupport": "4"}), ("full", {"FSR.Fsr4GpuSupport": "2"}))))
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
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "4"
    service.configure(APPID, {"model": "full"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "2"
    service.configure(APPID, {"model": "bogus"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "FSR.Fsr4GpuSupport") == "4"
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


def test_unified_fsr31_dll_counts_as_the_games_frame_generation(tmp_path):
    root = tmp_path / "Game"
    _write(root / "Game.exe", b"MZ")
    _write(root / "amd_fidelityfx_dx12.dll", b"ffx 3.1")
    inputs = games.analyze(root)["inputs"]
    assert inputs["fsr31"] and inputs["fsrfg"]


# ---- Heroic and Lutris shortcuts ------------------------------------------------------------

from upscalers import launchers


def test_launcher_shortcuts_are_recognised():
    assert launchers.identify('"flatpak"', 'run com.heroicgameslauncher.hgl --no-gui "heroic://launch?appName=Fortnite&runner=legendary"') == ("heroic", "Fortnite", "legendary")
    assert launchers.identify("/usr/bin/heroic", '"heroic://launch/gog/1207658924"') == ("heroic", "1207658924", "gog")
    assert launchers.identify('"/home/deck/.local/share/heroic/wrappers/legendary-Quail.desktop"', "") == ("heroic", "Quail", "legendary")
    assert launchers.identify('"lutris"', "'lutris:rungameid/42'") == ("lutris", "42", None)
    assert launchers.identify("/home/deck/.local/share/applications/lutris-witcher-3.sh", "") == ("lutris", "slug:witcher-3", None)
    assert launchers.identify("/games/Game.exe", "-dx12") is None


def test_heroic_game_gets_overrides_in_its_own_config(tmp_path):
    home = tmp_path
    game = tmp_path / "Games/Heroic/Quail"
    _write(game / "Binaries/Quail.exe", b"MZ")
    base = home / ".config/heroic"
    _write(base / "legendaryConfig/legendary/installed.json", json.dumps({
        "Quail": {"install_path": str(game), "executable": "Binaries/Quail.exe", "title": "Quail", "platform": "Windows"}}))
    _write(base / "GamesConfig/Quail.json", json.dumps({"Quail": {"enviromentOptions": [
        {"key": "WINEDLLOVERRIDES", "value": "winmm=n,b"}, {"key": "DXVK_HUD", "value": "1"}]}}))
    found = launchers.find(str(home), "heroic", "Quail", "legendary")
    assert found.root == game and found.exe == "Binaries/Quail.exe" and not found.native
    launchers.set_overrides(found, ["dxgi"])
    env = json.loads(found.config.read_text())["Quail"]["enviromentOptions"]
    assert {"key": "WINEDLLOVERRIDES", "value": "winmm=n,b;dxgi=n,b"} in env and {"key": "DXVK_HUD", "value": "1"} in env
    launchers.set_overrides(found, ["dxgi"], remove=True)
    env = json.loads(found.config.read_text())["Quail"]["enviromentOptions"]
    assert {"key": "WINEDLLOVERRIDES", "value": "winmm=n,b"} in env


def test_lutris_game_gets_wine_overrides_in_its_yaml(tmp_path):
    import sqlite3
    home = tmp_path
    data = home / ".local/share/lutris"
    (data / "games").mkdir(parents=True)
    with sqlite3.connect(data / "pga.db") as db:
        db.execute("CREATE TABLE games (id INTEGER, name TEXT, slug TEXT, configpath TEXT)")
        db.execute("INSERT INTO games VALUES (42, 'The Witcher 3', 'witcher-3', 'witcher-3-1700000000')")
    exe = _write(tmp_path / "Games/witcher/bin/x64_dx12/witcher3.exe", b"MZ")
    yml = data / "games/witcher-3-1700000000.yml"
    yml.write_text(f"game:\n  exe: {exe}\n  prefix: /home/deck/Games/witcher\nsystem:\n  env:\n    DXVK_ASYNC: '1'\nwine:\n  version: ge-proton\n")
    found = launchers.find(str(home), "lutris", "42")
    assert found.root == exe.parent and found.exe == "witcher3.exe"
    launchers.set_overrides(found, ["dxgi"])
    text = yml.read_text()
    assert "wine:\n  overrides:\n    dxgi: n,b\n  version: ge-proton" in text and "DXVK_ASYNC: '1'" in text
    launchers.set_overrides(found, ["dxgi"], remove=True)
    assert "overrides" not in yml.read_text() and "version: ge-proton" in yml.read_text()


def test_heroic_shortcut_installs_with_overrides_in_heroic(steam, fake_catalog, proc):
    home, _ = steam
    game = home / "Games/Heroic/Quail"
    _write(game / "Quail.exe", b"MZ" + b"\0" * 4096)
    base = home / ".var/app/com.heroicgameslauncher.hgl/config/heroic"
    _write(base / "legendaryConfig/legendary/installed.json", json.dumps({
        "Quail": {"install_path": str(game), "executable": "Quail.exe", "title": "Quail", "platform": "Windows"}}))
    hint = {"exe": '"flatpak"', "dir": "", "name": "Quail",
            "opts": 'run com.heroicgameslauncher.hgl --no-gui "heroic://launch?appName=Quail&runner=legendary"'}
    service = _service(steam, fake_catalog, proc)
    detail = service.game("3000000001", hint)
    assert detail["native"] is False and detail["analysis"]["exe"] == "Quail.exe"
    result = service.install("3000000001", {"build": "fsr-test"})
    assert result["overrides"] == [] and result["launcher"] == "heroic"
    assert (game / "dxgi.dll").read_bytes() == b"injector"
    env = json.loads((base / "GamesConfig/Quail.json").read_text())["Quail"]["enviromentOptions"]
    assert env == [{"key": "WINEDLLOVERRIDES", "value": "dxgi=n,b"}]
    removed = service.uninstall("3000000001")
    assert removed["overrides"] == [] and not (game / "dxgi.dll").exists()
    assert json.loads((base / "GamesConfig/Quail.json").read_text())["Quail"]["enviromentOptions"] == []


# ---- lsfg-vk ----------------------------------------------------------------------------------

from upscalers import lsfg


def _lsfg_bundle(root):
    for relative in lsfg.LAYER_FILES:
        _write(root / relative, relative.encode())
    _write(root / "bin/lsfg-vk-ui", b"ui")
    return root


def test_lsfg_installs_the_layer_and_writes_per_game_profiles(steam, tmp_path):
    home, _ = steam
    library = home / ".local/share/Steam"
    _write(library / "steamapps/appmanifest_993090.acf", '"AppState"\n{\n "appid" "993090"\n}\n')
    dll = _write(library / "steamapps/common/Lossless Scaling/lsfg-vk.dll", b"dll")
    tool = lsfg.Lsfg(str(home), tmp_path / "state")
    status = tool.install(_lsfg_bundle(tmp_path / "bundle"), "lsfg-vk-2.0.0")
    assert status["installed"] and status["lossless"] and status["dll"] == str(dll)
    assert not (home / ".local/bin/lsfg-vk-ui").exists()
    result = tool.set_game("123", "Game", {"multiplier": 3, "flow": "performance", "performance": True},
                           exe="bin/Game.exe")
    assert result["env"] == {"ENABLE_GAMESCOPE_WSI": "0", "LSFGVK_PROFILE": "pdc-123"}
    config = (home / lsfg.CONFIG).read_text()
    import tomllib
    parsed = tomllib.loads(config)
    assert parsed["global"]["dll"] == str(dll)
    assert parsed["profile"] == [{"name": "pdc-123", "active_in": ["Game.exe"], "multiplier": 3,
                                  "flow_scale": 0.5, "performance_mode": True}]
    assert tool.set_game("123", "Game", None)["env"] == {}
    # The game may still be running with LSFGVK_PROFILE=pdc-123: its profile stays, generating nothing.
    assert tomllib.loads((home / lsfg.CONFIG).read_text())["profile"] == [{"name": "pdc-123", "multiplier": 1}]
    with pytest.raises(lsfg.LsfgError, match="lsfg_invalid"):
        tool.set_game("123", "Game", {"multiplier": 7})
    tool.uninstall()
    assert not (home / ".local" / lsfg.LAYER_FILES[0]).exists() and not (home / lsfg.CONFIG).exists()


def test_lsfg_never_writes_over_another_tools_setup(steam, tmp_path):
    home, _ = steam
    _write(home / lsfg.CONFIG, "version = 2\n[global]\nallow_fp16 = true\n")
    tool = lsfg.Lsfg(str(home), tmp_path / "state")
    assert tool.status()["foreign"]
    with pytest.raises(lsfg.LsfgError, match="lsfg_foreign"):
        tool.install(_lsfg_bundle(tmp_path / "bundle"), "lsfg-vk-2.0.0")
    assert (home / lsfg.CONFIG).read_text().startswith("version = 2")
    with pytest.raises(lsfg.LsfgError, match="lsfg_missing"):
        tool.set_game("123", "Game", {"multiplier": 2})


class FakeHelix:
    """HelixSR's bridge as the service sees it: install/remove write what the real one writes."""

    def __init__(self, ready=True):
        self._ready = ready
        self.calls = []

    def ready(self):
        return self._ready

    def install(self, game):
        self.calls.append(("install",))
        exe = game / "bin/x64_dx12"
        _write(exe / "amd_fidelityfx_upscaler_dx12.original.dll", b"game fsr")
        _write(exe / "helixsr-install.json", "{}")
        return {"installed": "fsr", "exe_folder": str(exe), "log_path": str(exe / "helixsr.log")}

    def remove(self, game):
        self.calls.append(("remove",))
        exe = game / "bin/x64_dx12"
        for name in ("helixsr-install.json", "amd_fidelityfx_upscaler_dx12.original.dll"):
            (exe / name).unlink(missing_ok=True)
        return {"installed": None}


@pytest.fixture
def helix_catalog(monkeypatch, fake_catalog):
    zipped = Asset(catalog.HELIXSR_ARCHIVE, "HelixSR.zip", "0" * 64, 10, ("http://invalid",), )
    monkeypatch.setitem(catalog.ASSETS, zipped.id, zipped)
    for build in (
        Build("hlx-fsr4", "helixsr", "FSR 4", ("rdna2",), 3, 2, archive=zipped.id, engine="helixsr", way="fsr"),
    ):
        monkeypatch.setitem(catalog.BUILDS, build.id, build)
    return fake_catalog


def test_helixsr_fsr_drop_in_installs_verifies_and_removes(steam, helix_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()

    result = service.install(APPID, {"build": "hlx-fsr4"})

    assert result["overrides"] == []
    assert service.overview()["installs"][APPID]["status"] == "pending"
    detail = service.game(APPID)
    assert detail["analysis"]["foreign"] is False
    assert detail["fg_plan"] is None

    log = _write(target / "HLX_FSR.log", "[10:03:59.458000] [I] HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x800, max render 1280x800, flags 0x19\n")
    future = time.time() + 5
    os.utime(log, (future, future))
    verdict = service.verify(APPID)
    assert verdict["result"] == "active"
    assert verdict["facts"]["output"] == [1280, 800]

    _write(target / "helixsr.log", "x\n")
    service.uninstall(APPID)
    assert service.helix.calls[-1] == ("remove",)
    assert not (target / "helixsr.log").exists() and not (target / "HLX_FSR.log").exists()
    assert not (target / games.MANIFEST_DIR).exists()
    assert service.game(APPID)["install"] is None


def test_helixsr_status_breaks_when_its_files_go(steam, helix_catalog, proc):
    _, game = steam
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    service.install(APPID, {"build": "hlx-fsr4"})
    (game / "bin/x64_dx12/helixsr-install.json").unlink()
    assert service.overview()["installs"][APPID]["status"] == "broken"


def test_helixsr_fsr_needs_the_games_fsr_31(steam, helix_catalog, proc):
    _, game = steam
    (game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll").unlink()
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    with pytest.raises(UpscalerError, match="helixsr_no_fsr"):
        service.install(APPID, {"build": "hlx-fsr4"})


def test_switching_from_helixsr_to_optiscaler_removes_helixsr_first(steam, helix_catalog, proc):
    _, game = steam
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    service.install(APPID, {"build": "hlx-fsr4"})
    service.install(APPID, {"build": "fsr-test"})
    assert ("remove",) in service.helix.calls
    assert (game / "bin/x64_dx12/dxgi.dll").read_bytes() == b"injector"


def test_report_explains_a_helixsr_install(steam, helix_catalog, proc):
    _, game = steam
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    service.install(APPID, {"build": "hlx-fsr4"})
    log = _write(game / "bin/x64_dx12/HLX_FSR.log", "[10:03:59.458000] [I] HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x800, max render 1280x800, flags 0x19\n")
    future = time.time() + 5
    os.utime(log, (future, future))
    report = service.report()
    entry = report["games"][0]
    assert report["helixsr"]["release"] == "HelixSR-3.2.0"
    assert entry["helixsr_files"] is True
    assert entry["log_verdict"] == "active"
    assert "own runtime active" in entry["log_excerpt"][-1]


def test_helixsr_fsr_drop_in_never_claims_frame_generation(steam, helix_catalog, proc):
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    service.install(APPID, {"build": "hlx-fsr4", "fg": "on"})
    assert service.game(APPID)["install"]["options"]["fg"] == "off"
    assert service.game(APPID)["fg_plan"] is None


def test_lsfg_config_always_has_a_profile(steam, tmp_path):
    import tomllib
    home, _ = steam
    tool = lsfg.Lsfg(str(home), tmp_path / "state")
    tool.install(_lsfg_bundle(tmp_path / "bundle"), "lsfg-vk-2.0.0")
    assert tomllib.loads((home / lsfg.CONFIG).read_text())["profile"] == [{"name": "pdc-none"}]


def test_wiki_recipes_load_and_hand_written_ones_win():
    data = json.loads((Path(recipes.__file__).with_name("recipes_wiki.json")).read_text())
    assert data["source"].startswith("optiscaler-wiki@")
    for appid, entry in data["recipes"].items():
        assert appid.isdecimal()
        assert set(entry) <= {"name", "args", "proxy", "needs", "optipatcher", "status"}
        assert set(entry.get("needs", [])) <= {"reframework", "nvngx_dlss", "anti_cheat_off"}
    assert recipes.recipe_for("292030").exe == "bin/x64_dx12/witcher3.exe"
    wild_hearts = recipes.recipe_for("1938010")
    assert wild_hearts.proxy == "winmm.dll" and wild_hearts.source.startswith("optiscaler-wiki@")
    assert recipes.recipe_for("2246340").needs == ("reframework",)
    assert recipes.recipe_for("1230530").broken


def test_recipe_proxy_and_args_apply_unless_the_user_picked(steam, fake_catalog, proc, monkeypatch):
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, proxy="winmm.dll", args=("-dx12",)))
    service = _service(steam, fake_catalog, proc)
    result = service.install(APPID, {"build": "fsr-test"})
    assert result["overrides"] == ["winmm=n,b"] and result["args"] == ["-dx12"]
    assert service.game(APPID)["recipe_info"] == {"needs": [], "broken": False, "proxy": "winmm.dll", "args": ["-dx12"]}
    result = service.install(APPID, {"build": "fsr-test", "proxy": "version.dll"})
    assert result["overrides"] == ["version=n,b"]


def test_recipe_proxy_panel_cannot_install_is_left_out(steam, fake_catalog, proc, monkeypatch):
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, proxy="d3d12.dll"))
    service = _service(steam, fake_catalog, proc)
    assert service.install(APPID, {"build": "fsr-test"})["overrides"] == ["dxgi=n,b"]


@pytest.fixture
def proton_catalog(monkeypatch, fake_catalog):
    build = Build("proton-fsr4", "proton", "FSR 4", ("rdna2",), 3, 2, engine="proton")
    monkeypatch.setitem(catalog.BUILDS, build.id, build)
    return fake_catalog


def test_proton_fsr4_only_asks_proton_through_launch_options(steam, proton_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    before = sorted(p.name for p in target.iterdir())
    service = _service(steam, proton_catalog, proc)
    result = service.install(APPID, {"build": "proton-fsr4", "env": "FSR4_UPGRADE"})
    assert result["env"] == {"FSR4_UPGRADE": "1"} and result["overrides"] == []
    assert sorted(p.name for p in target.iterdir()) == before
    assert service.overview()["installs"][APPID]["status"] == "pending"
    assert service.verify(APPID)["result"] == "pending"
    assert service.uninstall(APPID)["env"] == {"FSR4_UPGRADE": None}
    with pytest.raises(UpscalerError, match="proton_env"):
        service.install(APPID, {"build": "proton-fsr4", "env": "LD_PRELOAD"})


def test_proton_fsr4_needs_the_games_fsr_31(steam, proton_catalog, proc):
    _, game = steam
    (game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll").unlink()
    service = _service(steam, proton_catalog, proc)
    with pytest.raises(UpscalerError, match="proton_no_fsr"):
        service.install(APPID, {"build": "proton-fsr4", "env": "FSR4_UPGRADE"})


def test_switching_from_optiscaler_to_proton_fsr4_takes_optiscaler_out(steam, proton_catalog, proc):
    _, game = steam
    service = _service(steam, proton_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    result = service.install(APPID, {"build": "proton-fsr4", "env": "FSR4_UPGRADE"})
    assert not (game / "bin/x64_dx12/dxgi.dll").exists()
    assert result["removed_overrides"] == ["dxgi=n,b"]


SAMPLE_INI = """; -------------------------------------------------------
[Upscalers]
; -------------------------------------------------------
; Select Upscaler for Dx12 games
; xess, fsr21, fsr22, ffx (FSR 2.3; 3.1; 4.x), dlss
; Default (auto) is DLSS when capable gpu
Dx12Upscaler=fsr31

[FrameGen]
; Enables Frame Generation
; true or false - Default (auto) is false
Enabled=false

; Selected FG Output
; nofg, fsrfg (needs FFX, or loader), xefg, dlssg - Default (auto) is nofg
FGOutput=nofg

; Older name kept by some builds
; nofg, fsrfg - Default (auto) is nofg
FGLegacy=fsrfg30

[Menu]
; Menu scale
; 0.5 - 2.0 - Default (auto) is 1.0
Scale=auto

; Show the FPS overlay
; true or false - Default (auto) is false
ShowFps=auto
"""


def test_ini_schema_reads_choices_and_defaults_from_optiscalers_comments():
    schema = ini.schema(SAMPLE_INI, managed={"FrameGen.Enabled"})
    sections = {s["name"]: s["keys"] for s in schema}
    fg = {k["key"]: k for k in sections["FrameGen"]}
    assert fg["Enabled"]["choices"] == ["auto", "true", "false"] and fg["Enabled"]["managed"]
    assert fg["FGOutput"]["choices"] == ["auto", "nofg", "fsrfg", "xefg", "dlssg"]
    assert fg["FGOutput"]["default"] == "nofg"
    assert fg["FGLegacy"]["choices"] == ["auto", "nofg", "fsrfg", "fsrfg30"]
    assert sections["Menu"][0]["choices"] is None and sections["Menu"][0]["value"] == "auto"
    assert sections["Menu"][1]["choices"] == ["auto", "true", "false"]
    assert sections["Upscalers"][0]["help"][0] == "Select Upscaler for Dx12 games"


def test_advanced_edits_keep_to_known_keys_and_values(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    (target / "OptiScaler.ini").write_text(SAMPLE_INI + "[Log]\nLogToFile=true\n")
    keys = {f"{s['name']}.{k['key']}": k for s in service.ini_schema(APPID)["sections"] for k in s["keys"]}
    assert keys["Log.LogToFile"]["managed"]
    service.set_ini(APPID, "Menu.ShowFps", "true")
    service.set_ini(APPID, "Menu.Scale", "1.25")
    text = (target / "OptiScaler.ini").read_text()
    assert ini.read(text, "Menu.ShowFps") == "true" and ini.read(text, "Menu.Scale") == "1.25"
    for dotted, value, code in (("Menu.ShowFps", "magic", "ini_value"), ("Menu.Nope", "1", "ini_key"),
                                ("FrameGen.FGOutput", "xefg", "ini_managed"), ("Log.LogToFile", "false", "ini_managed"),
                                ("Menu.Scale", "1\n[x]", "ini_value")):
        with pytest.raises(UpscalerError, match=code):
            service.set_ini(APPID, dotted, value)


def test_any_re_engine_game_gets_reframework_and_loses_the_warning(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    reframework = Asset("reframework-nightly", "REFramework.zip", hashlib.sha256(b"rf").hexdigest(), 2,
                        ("http://invalid",), member="dinput8.dll")
    monkeypatch.setitem(catalog.ASSETS, reframework.id, reframework)
    _write(Path(fake_catalog) / "cache" / reframework.sha256 / "unpacked/dinput8.dll", b"reframework")
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, needs=("reframework",)))
    _write(game / "re_chunk_000.pak")
    service = _service(steam, fake_catalog, proc)
    assert service.game(APPID)["recipe_info"]["needs"] == []
    result = service.install(APPID, {"build": "fsr-test"})
    assert (game / "bin/x64_dx12/dinput8.dll").read_bytes() == b"reframework"
    assert sorted(result["overrides"]) == ["dinput8=n,b", "dxgi=n,b"]


def test_another_tools_optiscaler_is_set_aside_and_can_come_back(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    _write(target / "dxgi.dll", b"MZ...OptiScaler build...")
    _write(target / "OptiScaler.ini", "[FSR]\n")
    _write(target / "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", b"x")
    _write(target / "FRAMEGEN_PATCH", "")
    _write(target / "winmm.dll", b"the game's own winmm")
    service = _service(steam, fake_catalog, proc)
    assert service.game(APPID)["analysis"]["foreign"]

    moved = service.adopt_foreign(APPID)
    assert sorted(moved["moved"]) == ["FRAMEGEN_PATCH", "OptiScaler", "OptiScaler.ini", "dxgi.dll"]
    detail = service.game(APPID)
    assert not detail["analysis"]["foreign"] and detail["foreign_backup"]
    assert (target / "winmm.dll").read_bytes() == b"the game's own winmm"
    service.install(APPID, {"build": "fsr-test"})
    with pytest.raises(UpscalerError, match="patched"):
        service.restore_foreign(APPID)
    service.uninstall(APPID)

    service.restore_foreign(APPID)
    assert (target / "dxgi.dll").read_bytes() == b"MZ...OptiScaler build..."
    assert (target / "OptiScaler/amd_fidelityfx_upscaler_dx12.dll").is_file()
    assert service.game(APPID)["foreign_backup"] is None


def test_helixsr_manager_install_gives_the_game_its_fsr_back(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    (target / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"helixsr")
    _write(target / "amd_fidelityfx_upscaler_dx12.original.dll", b"game fsr")
    _write(target / "helixsr-install.json", json.dumps({"helixsr": "1.8.1", "files": ["amd_fidelityfx_upscaler_dx12.dll"]}))
    service = _service(steam, fake_catalog, proc)
    service.adopt_foreign(APPID)
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"game fsr"
    assert not (target / "amd_fidelityfx_upscaler_dx12.original.dll").exists()
    service.restore_foreign(APPID)
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"helixsr"
    assert (target / "amd_fidelityfx_upscaler_dx12.original.dll").read_bytes() == b"game fsr"


def test_lsfg_from_another_tool_is_set_aside_then_restored(steam, tmp_path):
    home, _ = steam
    for relative in lsfg.LAYER_FILES:
        _write(home / ".local" / relative, b"theirs")
    _write(home / lsfg.CONFIG, "version = 2\n[[profile]]\nname = \"Bloodborne\"\n")
    tool = lsfg.Lsfg(str(home), tmp_path / "state")
    assert tool.status()["foreign"]
    tool.adopt_foreign()
    assert not tool.status()["foreign"] and tool.status()["foreign_backup"]
    assert not (home / lsfg.CONFIG).exists()
    tool.install(_lsfg_bundle(tmp_path / "bundle"), "lsfg-vk-2.0.0")
    with pytest.raises(lsfg.LsfgError, match="lsfg_installed"):
        tool.restore_foreign()
    tool.uninstall()
    tool.restore_foreign()
    assert (home / lsfg.CONFIG).read_text().startswith("version = 2")
    assert (home / ".local" / lsfg.LAYER_FILES[0]).read_bytes() == b"theirs"
    assert not tool.status()["foreign_backup"]


def test_a_game_without_a_bundled_recipe_uses_the_live_wiki_by_name(steam, fake_catalog, proc, monkeypatch):
    monkeypatch.setattr(recipes, "RECIPES", {})
    monkeypatch.setattr(recipes, "WIKI", {})
    service = _service(steam, fake_catalog, proc)
    service.wiki._rows = {"witcher": {"args": ["-dx12"], "needs": ["anti_cheat_off"]}}
    detail = service.game(APPID)
    assert detail["recipe_info"]["needs"] == ["anti_cheat_off"] and detail["recipe_info"]["args"] == ["-dx12"]


def test_unreal_plugin_libraries_deep_in_the_tree_are_found(tmp_path):
    root = tmp_path / "game"
    _write(root / "FSD/Binaries/Win64/FSD-Win64-Shipping.exe", b"MZ" + b"\0" * 4096 + b"ffxFsr2ContextCreate\0")
    _write(root / "FSD/Plugins/Nvidia/DLSS/Binaries/ThirdParty/Win64/nvngx_dlss.dll")
    _write(root / "Engine/Plugins/Runtime/Nvidia/Streamline/Binaries/ThirdParty/Win64/sl.interposer.dll")
    result = games.analyze(root)
    assert result["inputs"]["dlss"] == ["FSD/Plugins/Nvidia/DLSS/Binaries/ThirdParty/Win64/nvngx_dlss.dll"]
    assert "streamline" in result["inputs"]
    assert result["inputs"]["fsr2"] == ["FSD/Binaries/Win64/FSD-Win64-Shipping.exe"]
    assert games.shipped_upscalers(root) == ["DLSS", "FSR 2"]


def test_optipatcher_goes_into_optiscalers_plugins_for_games_that_support_it(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    patcher = Asset(catalog.OPTIPATCHER, "OptiPatcher_v0.42.asi", hashlib.sha256(b"op").hexdigest(), 2, ("http://invalid",))
    monkeypatch.setitem(catalog.ASSETS, patcher.id, patcher)
    _write(Path(fake_catalog) / "cache" / patcher.sha256 / patcher.filename, b"op")
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, optipatcher=True))
    service = _service(steam, fake_catalog, proc)
    assert service.game(APPID)["recipe"] is True
    service.install(APPID, {"build": "fsr-test"})
    target = game / "bin/x64_dx12"
    assert (target / "plugins/OptiPatcher.asi").read_bytes() == b"op"
    assert ini.read((target / "OptiScaler.ini").read_text(), "Plugins.LoadAsiPlugins") == "true"
    service.uninstall(APPID)
    assert not (target / "plugins").exists()


def test_wiki_optipatcher_flag_makes_a_recipe():
    recipe = recipes.from_facts("1", {"optipatcher": True}, "wiki")
    assert recipe is not None and recipe.optipatcher
