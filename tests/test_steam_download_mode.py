import os

from tdp.steam_download_mode import SteamDownloadModeHold, read_download_mode_limit
from tdp.types import RailReading, TdpObservation

DECK_TOML = """[tdp_limit]
method = "amdgpu_hwmon"
download_mode_limit = 6

[fan_speed]
hwmon = "steamdeck_hwmon"
download_mode_fan_speed = 2000

[tdp_limit.range]
min = 3
max = 15
"""


def _write(root, text):
    path = os.path.join(root, "usr/share/steamos-manager/devices")
    os.makedirs(path)
    with open(os.path.join(path, "steam-deck.toml"), "w") as handle:
        handle.write(text)


def _deck(pl2, pl3):
    return TdpObservation(
        readable=True,
        surfaces={"steamdeck-hwmon": {"pl2": RailReading(pl2), "pl3": RailReading(pl3)}},
    )


def test_reads_the_deck_download_mode_limit(tmp_path):
    _write(str(tmp_path), DECK_TOML)
    assert read_download_mode_limit(str(tmp_path)) == 6


def test_no_limit_without_config_or_key(tmp_path):
    assert read_download_mode_limit(str(tmp_path)) is None
    _write(str(tmp_path), '[tdp_limit]\nmethod = "amdgpu_hwmon"\n')
    assert read_download_mode_limit(str(tmp_path)) is None


def test_broken_config_is_ignored(tmp_path):
    _write(str(tmp_path), "[tdp_limit\ndownload_mode_limit = 6")
    assert read_download_mode_limit(str(tmp_path)) is None


def test_enters_when_an_outside_write_lands_on_the_download_limit():
    hold = SteamDownloadModeHold(6)
    assert hold.observe(_deck(6, 6), {"pl2": 15, "pl3": 15}, now=10.0) == "entered"
    assert hold.active
    assert hold.observe(_deck(6, 6), {"pl2": 15, "pl3": 15}, now=12.0) is None
    assert hold.active


def test_leaves_when_steamos_manager_restores_the_limit():
    hold = SteamDownloadModeHold(6)
    hold.observe(_deck(6, 6), {"pl2": 12, "pl3": 12}, now=10.0)
    assert hold.observe(_deck(12, 12), {"pl2": 12, "pl3": 12}, now=40.0) == "left"
    assert not hold.active
    assert hold.diagnostics()["last"] == {"entered_at": 10.0, "left_at": 40.0, "held_s": 30.0}


def test_own_target_at_the_limit_is_not_a_hold():
    hold = SteamDownloadModeHold(6)
    assert hold.observe(_deck(6, 6), {"pl2": 6, "pl3": 6}, now=1.0) is None
    assert not hold.active


def test_partial_or_other_values_are_not_a_hold():
    hold = SteamDownloadModeHold(6)
    assert hold.observe(_deck(6, 15), {"pl2": 15, "pl3": 15}, now=1.0) is None
    assert hold.observe(_deck(5, 5), {"pl2": 15, "pl3": 15}, now=1.0) is None
    assert hold.observe(TdpObservation(readable=False), {"pl2": 15}, now=1.0) is None
    assert not hold.active


def test_disabled_without_a_configured_limit():
    hold = SteamDownloadModeHold(None)
    assert hold.observe(_deck(6, 6), {"pl2": 15, "pl3": 15}, now=1.0) is None
    assert hold.diagnostics()["limit_w"] is None


def test_unreadable_observation_keeps_the_hold():
    hold = SteamDownloadModeHold(6)
    hold.observe(_deck(6, 6), {"pl2": 15, "pl3": 15}, now=1.0)
    assert hold.observe(TdpObservation(readable=False), {"pl2": 15}, now=2.0) is None
    assert hold.active


def test_release_clears_the_hold():
    hold = SteamDownloadModeHold(6)
    hold.observe(_deck(6, 6), {"pl2": 15, "pl3": 15}, now=1.0)
    assert hold.release(now=5.0) is True
    assert not hold.active
    assert hold.release(now=6.0) is False
