import pytest

from upscalers import catalog

EXACT = "fsr-4.1.2-lite-dgpu-dll"
LOSSY = "fsr-4.1.2-lite-dgpu-lossy-dll"


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
