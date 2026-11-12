import os

from tdp.steam_download_mode import (
    SteamDownloadModeHold,
    download_mode_handles,
    read_download_mode_limit,
)
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


TARGET = {"pl2": 15, "pl3": 15}


def _on():
    return True, "handles"


def _off():
    return False, "handles"


def _unknown():
    return None, None


def test_enters_when_steam_confirms_an_outside_write_on_the_limit():
    hold = SteamDownloadModeHold(6)
    assert hold.step(_deck(6, 6), TARGET, {"pl2": 15, "pl3": 15}, 1.0, _on) == "entered"
    assert hold.active and hold.holding


def test_our_own_write_at_the_limit_is_never_a_hold():
    hold = SteamDownloadModeHold(6)
    assert hold.step(_deck(6, 6), TARGET, {"pl2": 6, "pl3": 6}, 1.0, _on) is None
    assert hold.step(_deck(6, 6), {"pl2": 6, "pl3": 6}, None, 1.0, _on) is None
    assert not hold.holding


def test_partial_or_other_values_are_not_a_hold():
    hold = SteamDownloadModeHold(6)
    for observation in (_deck(6, 15), _deck(5, 5), TdpObservation(readable=False)):
        assert hold.step(observation, TARGET, None, 1.0, _on) is None
        assert not hold.holding


def test_disabled_without_a_configured_limit():
    hold = SteamDownloadModeHold(None)
    assert hold.step(_deck(6, 6), TARGET, None, 1.0, _on) is None
    assert not hold.holding
    assert hold.diagnostics()["limit_w"] is None


def test_waits_for_steam_to_confirm_before_writing_back():
    hold = SteamDownloadModeHold(6)
    assert hold.step(_deck(6, 6), TARGET, None, 1.0, _off) is None
    assert hold.holding and not hold.active
    assert hold.step(_deck(6, 6), TARGET, None, 3.0, _on) == "entered"
    assert hold.active


def test_unconfirmed_limit_is_reported_once_then_released():
    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 1.0, _unknown)
    assert hold.step(_deck(6, 6), TARGET, None, 6.5, _unknown) == "unconfirmed"
    assert not hold.holding
    assert hold.step(_deck(6, 6), TARGET, None, 7.0, _unknown) is None
    hold.step(_deck(15, 15), TARGET, None, 8.0, _unknown)
    assert hold.diagnostics()["pending_since"] is None


def test_leaves_when_steamos_manager_restores_the_limit():
    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 10.0, _on)
    assert hold.step(_deck(6, 6), TARGET, None, 12.0, _on) is None
    assert hold.step(TdpObservation(readable=False), TARGET, None, 13.0, _on) is None
    assert hold.active
    assert hold.step(_deck(12, 12), TARGET, None, 40.0, _on) == "left"
    assert not hold.active
    assert hold.diagnostics()["last"] == {
        "entered_at": 10.0, "left_at": 40.0, "held_s": 30.0, "why": "rails_changed",
        "source": "handles",
    }


def test_leaves_when_steam_says_the_mode_ended_without_a_restore():
    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 10.0, _on)
    assert hold.step(_deck(6, 6), TARGET, None, 15.0, _off) is None
    assert hold.step(_deck(6, 6), TARGET, None, 21.0, _off) == "left"
    assert hold.diagnostics()["last"]["why"] == "steam_left"
    for tick in range(10):
        assert hold.step(_deck(6, 6), TARGET, None, 22.0 + tick, _off) is None
        assert not hold.holding
    hold.step(_deck(15, 15), TARGET, None, 40.0, _off)
    assert hold.step(_deck(6, 6), TARGET, None, 50.0, _on) == "entered"


def test_stops_asking_steam_after_an_unconfirmed_limit():
    hold = SteamDownloadModeHold(6)
    calls = []

    def signal():
        calls.append(1)
        return None, None

    for tick in range(20):
        hold.step(_deck(6, 6), TARGET, None, 1.0 + tick, signal)
    assert len(calls) == 6


def test_fan_service_only_hold_has_a_time_cap():
    from tdp.steam_download_mode import FALLBACK_MAX_S

    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 0.0, lambda: (True, "fan_service"))
    assert hold.step(_deck(6, 6), TARGET, None, FALLBACK_MAX_S - 1, lambda: (True, "fan_service")) is None
    assert hold.step(_deck(6, 6), TARGET, None, FALLBACK_MAX_S, lambda: (True, "fan_service")) == "left"
    assert hold.diagnostics()["last"]["why"] == "timeout"
    assert hold.step(_deck(6, 6), TARGET, None, FALLBACK_MAX_S + 1, lambda: (True, "fan_service")) is None
    assert not hold.holding and hold.diagnostics()["count"] == 1

    confirmed = SteamDownloadModeHold(6)
    confirmed.step(_deck(6, 6), TARGET, None, 0.0, _on)
    assert confirmed.step(_deck(6, 6), TARGET, None, FALLBACK_MAX_S, _on) is None
    assert confirmed.active


def test_release_during_the_wait_lets_the_write_through():
    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 1.0, _unknown)
    assert hold.holding
    assert hold.release(now=2.0) is False
    assert not hold.holding
    assert hold.step(_deck(6, 6), TARGET, None, 3.0, _on) is None


def test_release_clears_the_hold():
    hold = SteamDownloadModeHold(6)
    hold.step(_deck(6, 6), TARGET, None, 1.0, _on)
    assert hold.release(now=5.0) is True
    assert not hold.active and not hold.holding
    assert hold.release(now=6.0) is False


def _session():
    from user_session import UserSession

    return UserSession(1000, "/run/user/1000", "deck")


def test_counts_steamos_manager_download_mode_handles(monkeypatch):
    import types

    monkeypatch.setattr("os.geteuid", lambda: 1000)
    for stdout, rc, expected in (
        ('a{su} 1 "steam" 3\n', 0, 1), ("as 0\n", 0, 0), ("", 1, None), ("garbage", 0, None),
    ):
        def run(*_args, _out=stdout, _rc=rc, **_kwargs):
            return types.SimpleNamespace(stdout=_out, returncode=_rc)

        assert download_mode_handles(_session(), run=run) == expected
    assert download_mode_handles(None) is None

    def broken(*_args, **_kwargs):
        raise OSError("no busctl")

    assert download_mode_handles(_session(), run=broken) is None


def test_reads_the_steamos_fan_service_state(monkeypatch):
    import subprocess
    import types

    from fans import software_loop

    cases = (
        ("LoadState=loaded\nActiveState=active\n", 0, True),
        ("LoadState=loaded\nActiveState=inactive\n", 0, False),
        ("LoadState=loaded\nActiveState=failed\n", 0, False),
        ("LoadState=not-found\nActiveState=inactive\n", 0, None),
        ("", 1, None),
    )
    for stdout, rc, expected in cases:
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, _out=stdout, _rc=rc, **k: types.SimpleNamespace(stdout=_out, returncode=_rc),
        )
        assert software_loop.jupiter_fan_control_active() is expected

    def broken(*_args, **_kwargs):
        raise OSError("no systemctl")

    monkeypatch.setattr(subprocess, "run", broken)
    assert software_loop.jupiter_fan_control_active() is None
