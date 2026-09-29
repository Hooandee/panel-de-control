import json
from dataclasses import replace

import pytest

from device_profiles import DEVICE_TABLE
from tdp.overshoot import REASSERT_S, SUSTAIN_S, VERIFY_S
from tdp.reconcile import ReconcileMemory
from test_tdp_guard_rpc import FakeBackend, plugin  # noqa: F401


class HiddenLimitBackend(FakeBackend):
    """Readback echoes the last write while the firmware may run its own
    maximum limits underneath, as the Ally X RC72LA does."""

    name = "firmware-attr:asus-armoury"

    def __init__(self, restore_on="any"):
        super().__init__()
        self.hidden = False
        self.restore_on = restore_on
        self.writes = []

    def set_levels(self, pl1, pl2, pl3, ac):
        previous = dict(self._levels)
        result = super().set_levels(pl1, pl2, pl3, ac)
        self.writes.append(dict(self._levels))
        changed = self._levels != previous
        if self.restore_on == "any" or (self.restore_on == "changed" and changed):
            self.hidden = False
        return result


class Meter:
    def __init__(self, backend, overshoot_w=43.0):
        self.backend = backend
        self.overshoot_w = overshoot_w

    def read_watts(self):
        if self.backend.hidden:
            return self.overshoot_w
        return float(self.backend._levels["pl1"])

    def read(self):
        return {"watts": self.read_watts(), "gpu_busy": 90}


ALLY_X = next(profile for profile in DEVICE_TABLE if profile.key == "rog_ally_x")


def start_game(plugin, backend, watts=20):  # noqa: F811
    plugin._device = ALLY_X
    plugin._tdp_backend = backend
    plugin._power_reader = Meter(backend)
    plugin._tdp_profiles.set_pl1("global", watts)
    plugin._current_appid = "3240220"
    plugin._execute_tdp_command(plugin._capture_tdp_command("game"))
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=0.0)
    backend.writes.clear()


def run(plugin, start, seconds, step=2.0):  # noqa: F811
    now = start
    while now < start + seconds:
        plugin._tdp_guard_tick(now=now)
        now += step
    return now


def overshoot_logs(plugin):  # noqa: F811
    return [
        json.loads(args[1])
        for args in plugin._test_logs["info"]
        if args and args[0] == "TDP overshoot %s"
    ]


def test_in_sync_rails_with_normal_draw_never_add_writes(plugin):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend)
    run(plugin, 10.0, 300.0)
    assert backend.writes == []
    assert overshoot_logs(plugin) == []


def test_hidden_firmware_limit_is_detected_and_restored(plugin):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend)
    backend.hidden = True
    now = run(plugin, 10.0, SUSTAIN_S + 6.0)
    assert backend.writes == [{"pl1": 20, "pl2": 20, "pl3": 20}]
    assert plugin._tdp_history[-1]["action"] == "overshoot-rewrite"
    run(plugin, now, 10.0)
    states = [entry["state"] for entry in overshoot_logs(plugin)]
    assert states == ["correcting", "restored"]
    assert plugin._tdp_ownership_state(plugin._tdp_observation)["overshoot"][
        "state"
    ] == "restored"
    assert plugin._tdp_profiles.effective("3240220")["pl1"] == 20


def test_same_value_write_ignored_falls_back_to_a_changed_value(plugin):  # noqa: F811
    backend = HiddenLimitBackend(restore_on="changed")
    start_game(plugin, backend)
    backend.hidden = True
    run(plugin, 10.0, SUSTAIN_S + VERIFY_S + 10.0)
    assert backend.writes[0] == {"pl1": 20, "pl2": 20, "pl3": 20}
    assert backend.writes[1] == {"pl1": 19, "pl2": 19, "pl3": 19}
    assert backend.writes[2] == {"pl1": 20, "pl2": 20, "pl3": 20}
    assert backend._levels == {"pl1": 20, "pl2": 20, "pl3": 20}
    assert backend.hidden is False
    assert overshoot_logs(plugin)[-1]["state"] == "restored"


def test_recurring_resets_escalate_to_bounded_reassert(plugin):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend)
    now = 10.0
    for _ in range(2):
        backend.hidden = True
        now = run(plugin, now, SUSTAIN_S + 10.0)
        now = run(plugin, now, 30.0)
    backend.writes.clear()
    run(plugin, now, 60.0, step=1.0)
    assert len(backend.writes) == pytest.approx(60.0 / REASSERT_S, abs=1)
    assert plugin._tdp_diagnostics()["overshoot"]["reassert_s"] == REASSERT_S


@pytest.mark.parametrize(
    "setup",
    ["no_game", "generic", "desktop", "write_only", "low_target"],
)
def test_ineligible_contexts_never_correct(plugin, setup):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend, watts=7 if setup == "low_target" else 20)
    if setup == "no_game":
        plugin._current_appid = None
    elif setup == "generic":
        plugin._device = replace(ALLY_X, is_generic=True)
    elif setup == "desktop":
        plugin._device = replace(ALLY_X, key="desktop_pc")
    elif setup == "write_only":
        backend.readback = False
    backend.hidden = True
    backend.writes.clear()
    run(plugin, 10.0, 120.0)
    corrections = [
        entry for entry in plugin._tdp_history
        if str(entry["action"]).startswith("overshoot-")
    ]
    assert corrections == []
    assert overshoot_logs(plugin) == []


def test_diagnostics_expose_the_monitor_state(plugin):  # noqa: F811
    backend = HiddenLimitBackend(restore_on="never")
    start_game(plugin, backend)
    backend.hidden = True
    run(plugin, 10.0, SUSTAIN_S + 4.0)
    diagnostics = plugin._tdp_diagnostics()["overshoot"]
    assert diagnostics["correcting"] is True
    assert diagnostics["last"]["ceiling_w"] == 20
    assert diagnostics["last"]["peak_w"] == 43.0


def test_ui_activity_flag_does_not_disable_detection(plugin):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend)
    plugin._ui_active = True
    backend.hidden = True
    run(plugin, 10.0, SUSTAIN_S + 6.0)
    assert backend.writes == [{"pl1": 20, "pl2": 20, "pl3": 20}]


def test_restored_notice_expires_even_when_detection_stops(plugin):  # noqa: F811
    backend = HiddenLimitBackend()
    start_game(plugin, backend)
    backend.hidden = True
    now = run(plugin, 10.0, SUSTAIN_S + 10.0)
    assert plugin._tdp_ownership_state(plugin._tdp_observation)["overshoot"]
    plugin._settings["tdp_control_enabled"] = False
    run(plugin, now, 120.0)
    assert plugin._tdp_ownership_state(plugin._tdp_observation)["overshoot"] is None
