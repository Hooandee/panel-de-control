import hashlib
import os
import time
from pathlib import Path

import pytest

from upscalers import catalog, games, ini, logread
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


def _service(steam, state, proc):
    home, _ = steam
    return UpscalerService(str(home), str(state), "rdna2", proc=str(proc))


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

    assert result["override"] == "dxgi=n,b"
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
            assert catalog.build_assets(build)[0].id == catalog.OPTISCALER_ARCHIVE
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
