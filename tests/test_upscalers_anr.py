import hashlib
from pathlib import Path

import pytest

from upscalers import catalog, diagnostics, ini, recipe_catalog
from upscalers.catalog import Asset, Build
from upscalers.service import UpscalerError, UpscalerService

APPID = "424242"
DLSSG = {"dlssg": ["nvngx_dlssg.dll"], "streamline": ["sl.interposer.dll"]}
PROVIDER = f"OptiScaler/custom/{catalog.ANR_PROVIDER}/dlssg"


def _write(path: Path, data: bytes | str = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def test_anr_is_a_route_only_for_dx12_dlss_fg_games_on_amd_handheld_gpus():
    routes = catalog.fg_routes("rdna3", DLSSG, ["d3d12"], streamline=2, generation=9)
    assert routes["anr"]["input"] == "nvngxfg" and routes["anr"]["provider"] == catalog.ANR_PROVIDER
    # Without a route of its own the game keeps the default: ANR is never picked for the user.
    assert catalog.fg_plan("rdna3", DLSSG, generation=10, apis=["d3d12"], streamline=2)["route"] == "game"
    assert "anr" not in catalog.fg_routes("rdna3", {"fsrfg": ["x"]}, ["d3d12"])
    assert "anr" not in catalog.fg_routes("rdna3", DLSSG, ["vulkan"], streamline=2)
    assert "anr" not in catalog.fg_routes("intel", DLSSG, ["d3d12"], streamline=2)


def test_overrides_hand_dlssg_back_whenever_anr_is_not_the_route():
    plan = catalog.fg_plan("rdna2", DLSSG, generation=10, apis=["d3d12"], streamline=2, route="anr")
    on = catalog.fg_overrides(plan, True, 10)
    assert on == {"FrameGen.Enabled": "auto", "FrameGen.FGInput": "nvngxfg", "FrameGen.FGOutput": "auto",
                  "FrameGen.FGNvngxReplacement": catalog.ANR_PROVIDER, "FrameGen.DisableHudless": "false"}
    game = catalog.fg_route_plan(plan, "game")
    assert catalog.fg_overrides(game, True, 10)["FrameGen.FGNvngxReplacement"] == "auto"
    assert catalog.fg_overrides(plan, False, 10)["FrameGen.DisableHudless"] == "auto"
    # OptiScaler 0.9 has neither key: its INI stays as before.
    assert "FrameGen.FGNvngxReplacement" not in catalog.fg_overrides(game, True)


def test_anr_build_keeps_an_optiscaler_10_install_and_otherwise_picks_fsr_412_on_10():
    assert catalog.anr_build("rdna3", "fsr-4.1.1") == "fsr-4.1.2-beta"
    assert catalog.anr_build("rdna2", "fsr-4.1.1-rdna2") == "fsr-4.1.1-rdna2"
    assert catalog.anr_build("rdna2", "fsr-4.1.2-dll") == "fsr-4.1.2-beta"
    assert catalog.anr_build("intel") is None and catalog.anr_build("rdna4") is None
    flags = {b["id"]: b["anr"] for b in catalog.describe("rdna3")}
    assert flags["fsr-4.1.2-beta"] and not flags["fsr-4.1.1"] and not flags["hlx-fsr4"]


@pytest.fixture
def anr_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(recipe_catalog, "bundled", lambda: recipe_catalog.Catalog(1, 0, {}, {}, {}))
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    _write(root / "steamapps/libraryfolders.vdf", '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n}\n' % root)
    _write(root / f"steamapps/appmanifest_{APPID}.acf",
           '"AppState"\n{\n "appid" "%s"\n "name" "Wizard"\n "installdir" "Wizard"\n "StateFlags" "4"\n}\n' % APPID)
    game = root / "steamapps/common/Wizard/Phoenix/Binaries/Win64"
    _write(game / "Wizard.exe", b"MZ" + b"\0" * 4096)
    _write(game / "nvngx_dlssg.dll")
    _write(game / "sl.interposer.dll")

    def asset(asset_id, content, generation=9):
        return Asset(asset_id, f"{asset_id}.7z", hashlib.sha256(content).hexdigest(), len(content), ("http://invalid",),
                     True, generation=generation)

    v9, v10, anr = asset(catalog.OPTISCALER_ARCHIVE, b"v9"), asset(catalog.OPTISCALER_BETA, b"v10", 10), asset(catalog.ANR_FG, b"anr", 10)
    monkeypatch.setattr(catalog, "ASSETS", {a.id: a for a in (v9, v10, anr)})
    monkeypatch.setattr(catalog, "BUILDS", {
        "old": Build("old", "fsr", "4.1.1", ("rdna3",), 3, 2),
        "new": Build("new", "fsr", "4.1.2", ("rdna3",), 3, 2, archive=catalog.OPTISCALER_BETA, extra_dir="OptiScaler"),
    })
    monkeypatch.setattr(catalog, "ANR_BUILDS", {"rdna3": "new"})
    state = tmp_path / "state"
    for archive, layout in ((v9, ""), (v10, "OptiScaler/")):
        unpacked = state / "cache" / archive.sha256 / "unpacked"
        _write(unpacked / "OptiScaler.dll", b"injector")
        _write(unpacked / "OptiScaler.ini", "[FrameGen]\nEnabled=auto\nFGInput=auto\nFGOutput=auto\n"
               "FGNvngxReplacement=auto\nDisableHudless=auto\n[Log]\nLogToFile=auto\n")
        _write(unpacked / f"{layout}D3D12Core.dll", b"core")
        _write(unpacked / ".complete", archive.sha256)
    unpacked = state / "cache" / anr.sha256 / "unpacked"
    _write(unpacked / f"{catalog.ANR_PROVIDER}/dlssg/nvngx_dlssg.dll", b"anr")
    _write(unpacked / f"{catalog.ANR_PROVIDER}/dlssg/programs/fg/pack.nrx", b"model")
    _write(unpacked / "install.sh", b"never runs")
    _write(unpacked / ".complete", anr.sha256)
    proc = tmp_path / "proc"
    proc.mkdir()
    service = UpscalerService(str(home), str(state), "rdna3", proc=str(proc))
    service.search = lambda term: []
    return service, game


def test_installing_anr_puts_its_provider_in_optiscalers_custom_folder_and_takes_it_out(anr_setup):
    service, game = anr_setup
    service.begin("install", APPID)
    service.install(APPID, {"build": "new", "fg": "on", "fg_route": "anr"})

    assert (game / PROVIDER / "nvngx_dlssg.dll").read_bytes() == b"anr"
    assert (game / PROVIDER / "programs/fg/pack.nrx").is_file()
    assert not (game / "install.sh").exists() and not (game / "OptiScaler/install.sh").exists()
    text = (game / "OptiScaler.ini").read_text()
    assert ini.read(text, "FrameGen.FGInput") == "nvngxfg"
    assert ini.read(text, "FrameGen.FGNvngxReplacement") == catalog.ANR_PROVIDER
    assert ini.read(text, "FrameGen.DisableHudless") == "false"
    install = service.state["games"][APPID]["install"]
    assert install["anr"] and install["options"]["fg_route"] == "anr"
    _write(game / PROVIDER / "nr_fg-1.log", "path=portable\nfeature created\n")
    report = diagnostics.game_report(service.home, APPID, service.state["games"][APPID])
    assert report["anr_log"]["provider"] and report["anr_log"]["tail"] == ["path=portable", "feature created"]
    assert report["ini"]["FrameGen.FGNvngxReplacement"] == catalog.ANR_PROVIDER

    service.configure(APPID, {"fg": "on", "fg_route": "game"})
    text = (game / "OptiScaler.ini").read_text()
    assert ini.read(text, "FrameGen.FGNvngxReplacement") == "auto" and ini.read(text, "FrameGen.FGInput") == "dlssg"
    service.configure(APPID, {"fg": "on", "fg_route": "anr"})
    service.configure(APPID, {"fg": "off", "fg_route": "anr"})
    assert ini.read((game / "OptiScaler.ini").read_text(), "FrameGen.FGNvngxReplacement") == "auto"

    service.uninstall(APPID)
    assert not (game / "OptiScaler").exists()


def test_anr_never_goes_in_on_optiscaler_09_or_by_configure_alone(anr_setup):
    service, game = anr_setup
    service.begin("install", APPID)
    with pytest.raises(UpscalerError) as refused:
        service.install(APPID, {"build": "old", "fg": "on", "fg_route": "anr"})
    assert refused.value.code == "anr_build"
    service.install(APPID, {"build": "new", "fg": "on", "fg_route": "game"})
    with pytest.raises(UpscalerError) as refused:
        service.configure(APPID, {"fg": "on", "fg_route": "anr"})
    assert refused.value.code == "anr_reinstall"
    assert not (game / PROVIDER).exists()
