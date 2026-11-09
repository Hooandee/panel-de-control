import json
import hashlib
import os
import shlex
import time
from pathlib import Path

import pytest

from upscalers import catalog, games, helixsr, ini, launchers, logread, lsfg, recipes
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
    _write(unpacked / "OptiScaler.ini", "[FSR]\nFsr4Update=auto\n[Log]\nLogToFile=auto\n[Spoofing]\n; true or false - Default (auto) is true\nDxgi=auto\n")
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
def dll_catalog(fake_catalog, monkeypatch):
    payload = b"standalone upscaler"
    asset = Asset("dll-test", "amd_fidelityfx_upscaler_dx12.dll", hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",))
    monkeypatch.setitem(catalog.ASSETS, asset.id, asset)
    monkeypatch.setitem(catalog.BUILDS, "dll-test", Build("dll-test", "fsr", "4.0.2c", ("rdna2",), 2, 3,
                        replace={asset.filename: asset.id}, engine="dll", way="fsr"))
    _write(Path(fake_catalog) / "cache" / asset.sha256 / asset.filename, payload)
    return fake_catalog


def test_dll_install_preserves_exact_paths_names_and_original_bytes(steam, dll_catalog, proc):
    _, game = steam
    original = game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"
    other = _write(game / "other/AMD_FIDELITYFX_UPSCALER_DX12.DLL", b"other original")
    log = _write(game / "OptiScaler.log", b"unrelated log")
    service = _service(steam, dll_catalog, proc)
    assert service.game(APPID)["analysis"]["dll_targets"] == [original.relative_to(game).as_posix(), other.relative_to(game).as_posix()]
    result = service.install(APPID, {"build": "dll-test"})
    assert result["overrides"] == [] and result["args"] == []
    assert original.read_bytes() == other.read_bytes() == b"standalone upscaler"
    assert not (game / "OptiScaler.ini").exists()
    assert not (original.parent / "dxgi.dll").exists()
    assert service.game(APPID)["install"]["status"] == "not_run"
    assert service.game(APPID)["fg_plan"] is None
    assert service.verify(APPID)["result"] == "not_run"
    assert service.diagnose(APPID)["log_verdict"] == "unverifiable"
    service.uninstall(APPID)
    assert original.read_bytes() == b"x"
    assert other.read_bytes() == b"other original"
    assert log.read_bytes() == b"unrelated log"
    assert not (game / games.MANIFEST_DIR).exists()


def test_dll_reinstall_after_a_game_update_backs_up_the_updated_file(steam, dll_catalog, proc):
    _, game = steam
    relative = "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "dll-test"})
    (game / relative).write_bytes(b"updated by game")
    assert service.game(APPID)["install"]["status"] == "broken"
    assert service.verify(APPID)["result"] == "broken"
    assert service.uninstall(APPID)["kept"] == [relative]
    assert (game / relative).read_bytes() == b"updated by game"
    assert (game / games.MANIFEST_DIR / "backup" / relative).read_bytes() == b"x"
    service.install(APPID, {"build": "dll-test"})
    assert (game / games.MANIFEST_DIR / "backup" / relative).read_bytes() == b"updated by game"
    service.uninstall(APPID)
    assert (game / relative).read_bytes() == b"updated by game"
    assert not (game / games.MANIFEST_DIR).exists()


def test_dll_mode_refuses_combined_library_and_symlink_instead_of_renaming(steam, dll_catalog, proc):
    _, game = steam
    original = game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"
    original.unlink()
    combined = _write(original.with_name("amd_fidelityfx_dx12.dll"), b"combined ABI")
    original.symlink_to(combined)
    service = _service(steam, dll_catalog, proc)
    assert service.game(APPID)["analysis"]["dll_targets"] == [combined.relative_to(game).as_posix()]
    with pytest.raises(UpscalerError, match="dll_unsupported"):
        service.install(APPID, {"build": "dll-test"})
    assert combined.read_bytes() == b"combined ABI"


def test_dll_reinstall_restores_original_before_replacing_and_has_no_ini_controls(steam, dll_catalog, proc):
    _, game = steam
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "dll-test"})
    service.install(APPID, {"build": "dll-test"})
    with pytest.raises(UpscalerError, match="dll_no_options"):
        service.configure(APPID, {"quality": "balanced"})
    with pytest.raises(UpscalerError, match="not_patched"):
        service.ini_schema(APPID)
    service.uninstall(APPID)
    assert (game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"


def test_dll_legacy_package_renames_loader_preserves_existing_fg_and_restores(steam, dll_catalog, proc, monkeypatch):
    _, game = steam
    folder = game / "bin/x64_dx12"
    provider = folder / "amd_fidelityfx_upscaler_dx12.dll"
    provider.unlink()
    legacy = _write(folder / "AMD_FIDELITYFX_DX12.DLL", b"original combined")
    fg = _write(folder / "amd_fidelityfx_framegeneration_dx12.dll", b"original separate FG")
    build = catalog.BUILDS["dll-test"]
    for name in ("amd_fidelityfx_loader_dx12.dll", "amd_fidelityfx_framegeneration_dx12.dll"):
        payload = name.encode()
        asset = Asset(name, "sdk.7z", hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",), member=name)
        monkeypatch.setitem(catalog.ASSETS, name, asset)
        monkeypatch.setitem(build.replace, name, name)
        _write(Path(dll_catalog) / "cache" / asset.sha256 / "unpacked" / name, payload)
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "dll-test"})
    assert legacy.read_bytes() == b"amd_fidelityfx_loader_dx12.dll"
    assert provider.read_bytes() == b"standalone upscaler"
    assert fg.read_bytes() == b"original separate FG"
    assert not (folder / "amd_fidelityfx_loader_dx12.dll").exists()
    service.install(APPID, {"build": "dll-test"})
    service.uninstall(APPID)
    assert legacy.read_bytes() == b"original combined"
    assert not provider.exists()
    assert fg.read_bytes() == b"original separate FG"


def test_dll_loader_package_adds_provider_beside_real_loader(steam, dll_catalog, proc, monkeypatch):
    _, game = steam
    folder = game / "bin/x64_dx12"
    provider = folder / "amd_fidelityfx_upscaler_dx12.dll"
    provider.unlink()
    name = "amd_fidelityfx_loader_dx12.dll"
    loader = _write(folder / name, b"old loader")
    payload = b"new loader"
    asset = Asset(name, "sdk.zip", hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",), member=name)
    monkeypatch.setitem(catalog.ASSETS, name, asset)
    monkeypatch.setitem(catalog.BUILDS["dll-test"].replace, name, name)
    _write(Path(dll_catalog) / "cache" / asset.sha256 / "unpacked" / name, payload)
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "dll-test"})
    assert loader.read_bytes() == payload
    assert provider.read_bytes() == b"standalone upscaler"
    service.uninstall(APPID)
    assert loader.read_bytes() == b"old loader"
    assert not provider.exists()


def test_dll_provider_only_preserves_existing_loader_and_ignores_optiscaler_logs(steam, dll_catalog, proc, monkeypatch):
    _, game = steam
    folder = game / "bin/x64_dx12"
    loader = _write(folder / "AMD_FIDELITYFX_LOADER_DX12.DLL", b"existing compatible loader")
    unrelated_log = _write(game / "OptiScaler.log", b"old log")
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "dll-test"})
    assert loader.read_bytes() == b"existing compatible loader"
    monkeypatch.setattr(logread, "read", lambda *args, **kwargs: pytest.fail("DLL mode must not read OptiScaler logs"))
    assert service.live(APPID) == {"result": "not_run", "resolution": None, "fg": None, "fg_toggle": False}
    service.install(APPID, {"build": "dll-test"})
    service.uninstall(APPID)
    assert loader.read_bytes() == b"existing compatible loader"
    assert unrelated_log.read_bytes() == b"old log"
    assert (folder / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"


def test_dll_provider_only_rejects_loader_without_provider_in_its_folder(steam, dll_catalog, proc):
    _, game = steam
    loader = _write(game / "different/amd_fidelityfx_loader_dx12.dll", b"loader without provider")
    service = _service(steam, dll_catalog, proc)
    with pytest.raises(UpscalerError, match="dll_unsupported"):
        service.install(APPID, {"build": "dll-test"})
    assert loader.read_bytes() == b"loader without provider"
    assert (game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"


def test_dll_mode_does_not_remove_optiscaler_when_its_provider_was_not_native(steam, dll_catalog, proc):
    _, game = steam
    folder = game / "bin/x64_dx12"
    (folder / "amd_fidelityfx_upscaler_dx12.dll").unlink()
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    assert service.game(APPID)["analysis"]["dll_targets"] == []
    with pytest.raises(UpscalerError, match="dll_no_target"):
        service.install(APPID, {"build": "dll-test"})
    assert service.game(APPID)["install"]["build"] == "fsr-test"
    assert (folder / "dxgi.dll").read_bytes() == b"injector"
    assert (folder / "OptiScaler.ini").is_file()


def test_dll_mode_can_replace_optiscaler_when_native_provider_is_backed_up(steam, dll_catalog, proc):
    _, game = steam
    folder = game / "bin/x64_dx12"
    service = _service(steam, dll_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    assert service.game(APPID)["analysis"]["dll_targets"] == ["bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"]
    service.install(APPID, {"build": "dll-test"})
    assert service.game(APPID)["install"]["engine"] == "dll"
    assert not (folder / "dxgi.dll").exists()
    service.uninstall(APPID)
    assert (folder / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"


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
            if build.engine == "dll":
                assert {asset.id for asset in catalog.build_assets(build)} == set(build.replace.values()) | set(build.legacy_replace.values())
                assert all(asset.id not in {catalog.OPTISCALER_ARCHIVE, catalog.OPTISCALER_BETA} for asset in catalog.build_assets(build))
            else:
                assert catalog.build_assets(build)[0].id == build.archive
                # HelixSR's ZIP is unpacked into the user's folder by helixsr.HelixSR, not by the cache.
                assert catalog.ASSETS[build.archive].archive == (build.engine != "helixsr")
    assert catalog.preferred_build("rdna2") == "fsr-4.1.2-beta"
    assert logread.verdict({"present": False}) == "not_run"


@pytest.mark.parametrize("api, expected", [("Dx12", "ffx"), ("Dx11", "ffx_12"), ("Vulkan", "ffx_12")])
def test_rdna2_411_uses_nightly_with_valve_provider_and_ffx_codes(api, expected):
    build = catalog.BUILDS["fsr-4.1.1-rdna2"]
    assert not build.injector
    assert build.archive == catalog.OPTISCALER_BETA
    assert "nightly-20261102/" in catalog.ASSETS[build.archive].urls[0]
    assert build.extra_dir == "OptiScaler"
    assert build.assets == ("amdxcffx64-4.1.1-valve", "amdxc64-rdna2")
    assert build.ini["FSR.Fsr4GpuSupport"] == "2"
    assert build.ini["Plugins.LoadCustomAmdxc64OnRdna2"] == "true"
    assert not {"FSR.Fsr4Update", "FSR.Fsr4ForceModel"} & build.ini.keys()
    assert ini.read(ini.apply("[FSR]\nUpscalerIndex=0\n", build.ini), "FSR.UpscalerIndex") == "1"
    key = f"Upscalers.{api}Upscaler"
    assert ini.read(ini.apply("", build.ini), key) == expected
    for legacy_id in ("fsr-4.1.1", "fsr-4.0.2c"):
        assert catalog.BUILDS[legacy_id].ini[key] == ("fsr31" if api == "Dx12" else "fsr31_12")


def test_fsr315_selects_first_provider_of_094_without_driver_update():
    build = catalog.BUILDS["fsr-3.1"]
    assert build.version == "3.1.5"
    assert build.archive == catalog.OPTISCALER_ARCHIVE
    assert "v0.9.4/" in catalog.ASSETS[build.archive].urls[0]
    configured = ini.apply("[FSR]\nUpscalerIndex=1\nFsr4Update=true\n", build.ini)
    assert ini.read(configured, "FSR.UpscalerIndex") == "0"
    assert ini.read(configured, "FSR.Fsr4Update") == "false"
    assert ini.read(configured, "Upscalers.Dx12Upscaler") == "fsr31"


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
    assert service.compatibility([APPID, "999"]) == {APPID: {"native": False, "inputs": ["DLSS", "FSR 3.1"], "preferred": "fsr-4.1.2-beta"}}


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
    assert facts["initial_resolution"] == {"render": [936, 624], "output": [1440, 960]}
    assert "resolution" not in facts
    assert facts["resolution_source"] == "initialization_only"
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
    assert game_report["steam"]["compat_tool"] == "proton_experimental"
    assert "launch_options" not in game_report["steam"]
    assert game_report["steam"]["launch_diagnostics"]["command_placeholder"] is True
    assert game_report["steam"]["launch_diagnostics"]["dll_overrides"] == [{"name": "dxgi", "mode": "n,b"}]
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

    log.write_text("[I] FrameGen.FGInput: fsrfg\n")
    os.utime(log, (future, future))
    assert service.live(APPID)["fg"] is None
    log.write_text("[I] FSRFG_Dx12::Deactivate D3D12_Configure Enabled: false, result: FFX_API_RETURN_OK (0)\n")
    os.utime(log, (future, future))
    assert service.live(APPID)["fg"] is False
    log.write_text("[W] XeFGInputs::Redirect OptiScaler's library is missing exports of the game's, not redirecting\n"
                   "[I] XeFGInputs::Hook XeFG passthrough: false\n")
    os.utime(log, (future, future))
    assert service.live(APPID)["fg"] is None
    assert service.live(APPID)["fg_toggle"] is False


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
    assert result["env"] == {"ENABLE_GAMESCOPE_WSI": "0", "LSFGVK_PROFILE": "pdc-123",
                             "LSFGVK_CONFIG": shlex.quote(str(home / lsfg.CONFIG))}
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
    assert tool.uninstall()["cleared"] == ["123"]
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
        self.release = Path("HelixSR-3.2.0")

    def ready(self):
        return self._ready

    def digest(self):
        return None

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
        assert set(entry) <= {"name", "args", "proxy", "needs", "optipatcher", "status", "inputs", "page", "page_facts"}
        assert set(entry.get("needs", [])) <= set(recipes.NEEDS)
    assert len(data["recipes"]) > 500
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
    info = service.game(APPID)["recipe_info"]
    assert {k: info[k] for k in ("needs", "broken", "proxy", "args")} == {"needs": [], "broken": False, "proxy": "winmm.dll", "args": ["-dx12"]}
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


def test_helixsr_manager_install_is_preserved_until_full_adoption_supported(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    (target / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"helixsr")
    _write(target / "amd_fidelityfx_upscaler_dx12.original.dll", b"game fsr")
    marker = json.dumps({"helixsr": "1.8.1", "files": ["amd_fidelityfx_upscaler_dx12.dll"]})
    _write(target / "helixsr-install.json", marker)
    service = _service(steam, fake_catalog, proc)
    with pytest.raises(UpscalerError, match="foreign_helix"):
        service.adopt_foreign(APPID)
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"helixsr"
    assert (target / "amd_fidelityfx_upscaler_dx12.original.dll").read_bytes() == b"game fsr"
    assert (target / "helixsr-install.json").read_text() == marker
    assert not service._game_state(APPID).get("foreign_backup")


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
    # The list only opens the exe when no library says it already; the game page always does.
    assert games.shipped_upscalers(root) == ["DLSS"]


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


def test_the_resolver_never_sets_aside_panels_own_install(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    with pytest.raises(UpscalerError, match="still_patched"):
        service.adopt_foreign(APPID)


def test_the_exe_is_only_searched_when_no_library_was_found(tmp_path, monkeypatch):
    root = tmp_path / "game"
    _write(root / "Game.exe", b"MZ" + b"\0" * 64)
    _write(root / "nvngx_dlss.dll")
    monkeypatch.setattr(games, "embedded_upscalers", lambda exe: pytest.fail("must not scan"))
    assert games.shipped_upscalers(root) == ["DLSS"]


def test_files_panel_leaves_in_a_game_belong_to_the_games_owner(steam, fake_catalog, proc, monkeypatch):
    from upscalers import service as service_module
    _, game = steam
    target = game / "bin/x64_dx12"
    owned = []
    monkeypatch.setattr(service_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(service_module.os, "chown", lambda path, uid, gid, follow_symlinks=True: owned.append(Path(path)))
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    for name in ("dxgi.dll", "OptiScaler.ini", "amdxcffx64.dll", "D3D12_Optiscaler", ".pdc-upscaler/manifest.json"):
        assert target / name in owned, name


def test_re_engine_games_move_optiscalers_menu_off_reframeworks_insert(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    reframework = Asset("reframework-nightly", "REFramework.zip", hashlib.sha256(b"rf").hexdigest(), 2,
                        ("http://invalid",), member="dinput8.dll")
    monkeypatch.setitem(catalog.ASSETS, reframework.id, reframework)
    _write(Path(fake_catalog) / "cache" / reframework.sha256 / "unpacked/dinput8.dll", b"reframework")
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID))
    _write(game / "re_chunk_000.pak")
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    assert ini.read((game / "bin/x64_dx12/OptiScaler.ini").read_text(), "Menu.ShortcutKey") == "0x24"
    pressed = []
    service.press = pressed.append
    _write(proc / "77/cmdline", f"{game}/bin/x64_dx12/witcher3.exe")
    service.press_key(APPID, "menu")
    service.press_key(APPID, "fg")
    assert pressed == ["home", "fg"]


def test_a_failed_switch_still_reports_what_the_old_install_left(steam, helix_catalog, proc):
    service = _service(steam, helix_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})

    class Broken(FakeHelix):
        def install(self, game):
            raise helixsr.HelixError("helixsr_failed", "bridge broke")

    service.helix = Broken()
    service.begin("install", APPID)
    service.run(service.install, APPID, {"build": "hlx-fsr4"})
    job = service.job()
    assert job["state"] == "error" and job["leftover"]["removed_overrides"] == ["dxgi=n,b"]
    assert service.game(APPID)["install"] is None


def test_helixsr_comes_out_even_when_its_release_is_gone(steam, helix_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, helix_catalog, proc)
    service.helix = FakeHelix()
    service.install(APPID, {"build": "hlx-fsr4"})
    (target / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"hlx")
    (target / "helixsr-install.json").write_text(json.dumps({"files": ["amd_fidelityfx_upscaler_dx12.dll"]}))
    service.helix = FakeHelix(ready=False)
    service.uninstall(APPID)
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"game fsr"
    assert not (target / "helixsr-install.json").exists()
    assert service.game(APPID)["install"] is None


def test_removal_leaves_overrides_the_user_already_had(steam, fake_catalog, proc):
    _, game = steam
    _write(game / "bin/x64_dx12/dxgi.dll", b"reshade")
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    service.record_added_args(APPID, ["--launcher-skip"], [], [])
    assert service.uninstall(APPID)["overrides"] == []
    service.install(APPID, {"build": "fsr-test"})
    service.record_added_args(APPID, [], ["dxgi=n,b"], [])
    assert service.uninstall(APPID)["overrides"] == ["dxgi=n,b"]


def test_hand_edits_survive_a_repair(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    (target / "OptiScaler.ini").write_text((target / "OptiScaler.ini").read_text() + SAMPLE_INI)
    service.set_ini(APPID, "Menu.ShowFps", "true")
    service.install(APPID, {"build": "fsr-test"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "Menu.ShowFps") == "true"


def test_monster_hunter_wilds_turns_dxgi_spoofing_off_and_still_gets_reframework(tmp_path):
    root = tmp_path / "MonsterHunterWilds"
    _write(root / "re_chunk_000.pak")
    recipe = recipes.with_engine(recipes.recipe_for("2246340"), "2246340", root)
    assert recipe.ini == {"Spoofing.Dxgi": "false", "Menu.ShortcutKey": "0x24"}
    assert recipe.files == {"dinput8.dll": "reframework-nightly"} and recipe.menu_key == "home"


def test_no_quality_leaves_the_games_own_scaling_mode_alone():
    from upscalers.service import _option_overrides
    assert _option_overrides({"quality": None})["QualityOverrides.QualityRatioOverrideEnabled"] == "false"
    forced = _option_overrides({"quality": "ultra"})
    assert forced["QualityOverrides.QualityRatioOverrideEnabled"] == "true"
    assert forced["QualityOverrides.QualityRatioBalanced"] == "3.00"


def test_native_quality_renders_at_screen_resolution():
    from upscalers.service import _option_overrides
    native = _option_overrides({"quality": "native"})
    assert native["QualityOverrides.QualityRatioOverrideEnabled"] == "true"
    assert native["QualityOverrides.QualityRatioPerformance"] == "1.00"


def test_wiki_page_settings_apply_but_panel_keys_and_hand_edits_win(steam, fake_catalog, proc, monkeypatch):
    recipe = recipes.Recipe(APPID, status="works", wiki_settings={"Dxgi": "false", "NoSuchKey": "1"},
                            wiki_suggestions={"HUDFix": "true"})
    monkeypatch.setitem(recipes.RECIPES, APPID, recipe)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    target = Path(service.game(APPID)["install"]["target"])
    text = (target / "OptiScaler.ini").read_text()
    assert ini.read(text, "Spoofing.Dxgi") == "false"
    assert "NoSuchKey" not in text
    assert "Spoofing.Dxgi" not in service.game(APPID)["install"]["managed"]
    service.set_ini(APPID, "Dxgi", "true")
    service.install(APPID, {"build": "fsr-test"})
    assert ini.read((target / "OptiScaler.ini").read_text(), "Spoofing.Dxgi") == "true"
    assert service.game(APPID)["recipe_info"]["suggestions"] == {"HUDFix": "true"}


def test_appimage_shortcut_on_the_desktop_is_a_linux_game_not_the_desktop_folder(steam, fake_catalog, proc):
    home, _ = steam
    desktop = home / "Desktop"
    _write(desktop / "HelixSR/amd_fidelityfx_upscaler_dx12.dll", b"x")
    _write(desktop / "HelixSR/setup/tool.exe", b"MZ" + b"\0" * 64)
    app = _write(desktop / "Uncharted-x86_64.appimage", b"\x7fELF")
    shortcut_id = 2163226583
    _write(home / ".local/share/Steam/userdata/123/config/shortcuts.vdf", _shortcuts_vdf([
        {"appid": shortcut_id, "name": "Uncharted", "exe": f'"{app}"', "start": f'"{desktop}"'},
    ]))
    service = _service(steam, fake_catalog, proc)
    assert service.compatibility([str(shortcut_id)])[str(shortcut_id)] == {"native": True, "inputs": [], "preferred": "fsr-4.1.2-beta"}
    with pytest.raises(UpscalerError):
        service.install(str(shortcut_id), {"build": "fsr-test"})
    assert not (desktop / "HelixSR/setup/dxgi.dll").exists()


def _running(proc, game):
    _write(proc / "4242/cmdline", f"Z:{game}/bin/x64_dx12/witcher3.exe".replace("/", "\\"))


def test_quality_changes_while_running_are_saved_for_the_next_launch(steam, fake_catalog, proc):
    home, game = steam
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    target = Path(service.game(APPID)["install"]["target"])
    _running(proc, game)
    result = service.configure(APPID, {"build": "fsr-test", "quality": "performance", "sharpness": "high"})
    assert result["live"] is False
    assert ini.read((target / "OptiScaler.ini").read_text(), "QualityOverrides.QualityRatioOverrideEnabled") == "true"
    with pytest.raises(UpscalerError, match="running"):
        service.configure(APPID, {"build": "fsr-test", "quality": "quality", "sharpness": "soft", "fg": "on"})


def test_quality_change_while_running_keeps_the_other_options(steam, fake_catalog, proc):
    home, game = steam
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test", "sharpness": "high"})
    _running(proc, game)
    service.configure(APPID, {"build": "fsr-test", "quality": "balanced", "sharpness": "high"})
    assert service.game(APPID)["install"]["options"] == {
        "quality": "balanced", "sharpness": "high", "fg": "off", "fg_route": None, "model": None}


# ---- OptiScaler generation per game ---------------------------------------------------------

LOADER_INPUTS = {"fsr31": ["bin/x64_dx12/amd_fidelityfx_loader_dx12.dll", "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"]}


def test_ffx_loader_games_get_optiscaler_10_for_xess():
    xess = catalog.for_game(catalog.BUILDS["xess"], LOADER_INPUTS, "intel")
    assert xess.archive == catalog.OPTISCALER_BETA
    assert xess.extra_dir == "OptiScaler"
    assert xess.ini == {"Upscalers.Dx12Upscaler": "xess", "Upscalers.Dx11Upscaler": "xess_12",
                        "Upscalers.VulkanUpscaler": "xess", "FSR.Fsr4GpuSupport": "4"}


def test_other_games_and_builds_keep_their_optiscaler():
    plain = {"fsr31": ["amd_fidelityfx_dx12.dll"]}
    assert catalog.for_game(catalog.BUILDS["xess"], plain, "intel") is catalog.BUILDS["xess"]
    for build_id in ("fsr-4.1.1-rdna2", "fsr-4.0.2c", "fsr-4.1.2-beta", "hlx-fsr4", "proton-fsr4"):
        assert catalog.for_game(catalog.BUILDS[build_id], LOADER_INPUTS, "intel") is catalog.BUILDS[build_id]
    assert catalog.for_game(catalog.BUILDS["fsr-3.1"], LOADER_INPUTS, "rdna3") is catalog.BUILDS["fsr-3.1"]


def test_fsr31_moves_to_optiscaler_10_away_from_amd():
    fsr31 = catalog.for_game(catalog.BUILDS["fsr-3.1"], LOADER_INPUTS, "intel")
    assert fsr31.archive == catalog.OPTISCALER_BETA
    assert "FSR.Fsr4Update" not in fsr31.ini
    assert fsr31.ini["Upscalers.Dx12Upscaler"] == "fsr31"
    assert fsr31.ini["FSR.Fsr4GpuSupport"] == "4"


def test_generation_follows_the_archive_the_install_used():
    from upscalers.service import _generation

    assert _generation({"build": "xess"}) == 9
    assert _generation({"build": "xess", "archive": catalog.OPTISCALER_BETA}) == 10


def test_restoring_another_tools_lsfg_never_drops_a_file_that_came_back(steam, tmp_path):
    home, _ = steam
    for relative in lsfg.LAYER_FILES:
        _write(home / ".local" / relative, b"theirs")
    _write(home / lsfg.CONFIG, "version = 2\n")
    tool = lsfg.Lsfg(str(home), tmp_path / "state")
    tool.adopt_foreign()
    _write(home / lsfg.CONFIG, "version = 3\n")
    tool.restore_foreign()
    assert (home / lsfg.CONFIG).read_text() == "version = 3\n"
    assert tool.status()["foreign_backup"]
    (home / lsfg.CONFIG).unlink()
    tool.restore_foreign()
    assert (home / lsfg.CONFIG).read_text() == "version = 2\n"
    assert not tool.status()["foreign_backup"]


@pytest.mark.parametrize("build, dx11, vulkan", [("fsr-3.1", "fsr31", "fsr31"), ("xess", "xess_12", "xess")])
def test_dx11_and_vulkan_games_run_the_chosen_upscaler(build, dx11, vulkan):
    ini = catalog.BUILDS[build].ini
    assert (ini["Upscalers.Dx11Upscaler"], ini["Upscalers.VulkanUpscaler"]) == (dx11, vulkan)


def test_fp8_sdk_providers_say_they_may_fall_back_off_rdna4():
    described = {item["id"]: item for item in catalog.describe("rdna3")}
    assert described["fsr-4.1.2-dll"]["may_fallback"] == "3.1.6"
    assert described["fsr-4.1.2-lite-igpu-dll"]["may_fallback"] is None
    assert {item["id"]: item for item in catalog.describe("rdna4")}["fsr-4.1.2-dll"]["may_fallback"] is None
