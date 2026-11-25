import pytest

from upscalers import catalog
from upscalers.service import UpscalerService

EXACT = "fsr-4.1.2-lite-dgpu-dll"
LOSSY = "fsr-4.1.2-lite-dgpu-lossy-dll"
PROVIDER = "amd_fidelityfx_upscaler_dx12.dll"
URL = "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/dll-2026-11-22/fsr4.1.2-cyboman-rx7000-2026-11-22.7z"


@pytest.mark.parametrize("build_id,model,member", [
    (EXACT, "lite", "4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll"),
    (LOSSY, "lossy", "4.1.2l-lossy/amd_fidelityfx_upscaler_dx12.dll"),
])
def test_dgpu_builds_pin_the_rx7000_archive(build_id, model, member):
    build = catalog.BUILDS[build_id]
    asset = catalog.ASSETS[build.replace[PROVIDER]]
    assert build.engine == "dll" and build.version == "4.1.2"
    assert build.models == ((model, {}),)
    assert asset.filename == "fsr4.1.2-cyboman-rx7000-2026-11-22.7z"
    assert asset.size == 13284673
    assert asset.sha256 == "bcd719dca0bfb791aec8987bad796eceb65fc887b3d1d45a4969d7b55e6f195d"
    assert asset.member == member
    assert asset.urls == (URL,)
    assert build.legacy_replace == catalog.BUILDS["fsr-4.1.2-lite-dll"].legacy_replace


@pytest.mark.parametrize("gpu,device,expected", [
    ("rdna3", "steam_machine", True),
    ("rdna4", "steam_machine", False),
    ("rdna3", "rog_ally", False),
    ("rdna3", "", False),
    ("rdna2", "steam_deck_lcd", False),
])
def test_dgpu_builds_only_on_steam_machine(gpu, device, expected):
    for build_id in (EXACT, LOSSY):
        assert catalog.build_supported(catalog.BUILDS[build_id], gpu, device) is expected


def test_igpu_build_stays_off_steam_machine_and_lossy_is_never_preferred():
    assert not catalog.build_supported(catalog.BUILDS["fsr-4.1.2-lite-igpu-dll"], "rdna3", "steam_machine")
    assert catalog.preferred_build("rdna3") not in (EXACT, LOSSY)


def test_steam_machine_overview_offers_both(tmp_path):
    service = UpscalerService(str(tmp_path), str(tmp_path / "state"), "rdna3", device="steam_machine")
    rows = {row["id"]: row for row in service.overview()["builds"]}
    assert rows[EXACT]["supported"] and rows[LOSSY]["supported"]
    assert rows[LOSSY]["models"] == ["lossy"]
    assert not rows["fsr-4.1.2-lite-igpu-dll"]["supported"]
