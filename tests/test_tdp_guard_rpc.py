import asyncio
import importlib
import json
import sys
import types
from dataclasses import replace

import pytest

from tdp.backend import TDPBackend
from tdp.reconcile import ReconcileMemory
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


class FakeBackend(TDPBackend):
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self.set_levels_calls = 0
        self.live_max = 35
        self._levels = {"pl1": 15, "pl2": 15, "pl3": 15}
        self._legacy_levels = None
        self._profile = "custom"

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {
            "pl1": {"min": 5, "max": 35},
            "pl2": {"min": 5, "max": 42},
            "pl3": {"min": 5, "max": 49},
        }

    def set_tdp(self, watts, ac):
        return self.set_levels(watts, watts, watts, ac)

    def set_levels(self, pl1, pl2, pl3, ac):
        self.set_levels_calls += 1
        self._levels = {
            "pl1": min(int(pl1), self.live_max),
            "pl2": int(pl2),
            "pl3": int(pl3),
        }
        if self._legacy_levels is not None:
            self._legacy_levels = dict(self._levels)
        return TdpResult(pl1, self._levels["pl1"], True, "")

    def read_applied(self):
        return self._levels["pl1"]

    def observe(self):
        surfaces = {
            self.name: {
                "pl1": RailReading(
                    self._levels["pl1"],
                    5,
                    self.live_max,
                ),
                "pl2": RailReading(self._levels["pl2"], 15, 42),
                "pl3": RailReading(self._levels["pl3"], 15, 49),
            },
        }
        if self._legacy_levels is not None:
            surfaces["legacy"] = {
                rail: RailReading(value)
                for rail, value in self._legacy_levels.items()
            }
        return TdpObservation(
            readable=True,
            surfaces=surfaces,
        )

    def set_surface(self, surface, **levels):
        if surface == "armoury":
            self._levels.update(levels)
        elif surface == "legacy":
            if self._legacy_levels is None:
                self._legacy_levels = dict(self._levels)
            self._legacy_levels.update(levels)

    def surface(self, surface):
        levels = (
            self._levels
            if surface == "armoury"
            else self._legacy_levels
        )
        return dict(levels) if levels is not None else None

    def profile_choices(self):
        return ["low-power", "balanced", "performance", "custom"]

    def set_profile(self, mode):
        self._profile = mode
        return True


class FakeFan:
    supported = True
    name = "fake-fan"

    def read_state(self):
        return {
            "supported": True,
            "source": "fake",
            "pwm_max": 255,
            "fans": [],
        }

    def apply_curve_all(self, points):
        pass

    def set_auto(self, points):
        pass

    def restore_auto(self):
        pass


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    logs = {
        "info": [],
        "warning": [],
        "error": [],
        "exception": [],
    }
    fake.logger = types.SimpleNamespace(
        info=lambda *a, **k: logs["info"].append(a),
        warning=lambda *a, **k: logs["warning"].append(a),
        error=lambda *a, **k: logs["error"].append(a),
        exception=lambda *a, **k: logs["exception"].append(a),
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    import tdp.factory as factory

    monkeypatch.setattr(
        factory,
        "select_backend",
        lambda device, **kw: FakeBackend(),
    )
    import fans.control as fan_control

    monkeypatch.setattr(
        fan_control,
        "select_fan_backend",
        lambda device, **kw: FakeFan(),
    )
    import lifecycle

    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    instance = main.Plugin()
    instance._init()
    instance._test_logs = logs
    return instance


def test_stale_generation_never_writes(plugin):
    old = plugin._capture_tdp_command("old")
    plugin._capture_tdp_command("new")
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(old)
    assert plugin._tdp_backend.set_levels_calls == 0
    assert result.detail == "stale-generation"


def test_command_preserves_requested_but_applies_live_target(plugin):
    plugin._tdp_profiles.set_pl1("global", 25)
    plugin._tdp_backend.live_max = 15
    command = plugin._capture_tdp_command("manual")
    result = plugin._execute_tdp_command(command)
    assert result.requested_w == 25
    assert result.applied_w == 15
    assert plugin._tdp_profiles.effective(None)["pl1"] == 25
    assert plugin._tdp_targets.requested["pl1"] == 25
    assert plugin._tdp_targets.target["pl1"] == 15


def test_guard_recovers_requested_when_live_ceiling_returns(plugin):
    plugin._tdp_profiles.set_pl1("global", 25)
    plugin._tdp_backend.live_max = 15
    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))
    assert plugin._tdp_targets.target["pl1"] == 15
    plugin._tdp_backend.live_max = 35
    _reset_guard_memory(plugin)
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    assert plugin._tdp_targets.requested["pl1"] == 25
    assert plugin._tdp_targets.target["pl1"] == 25
    assert plugin._tdp_backend._levels["pl1"] == 25


def test_command_drops_generation_changed_during_observation(
    plugin,
    monkeypatch,
):
    command = plugin._capture_tdp_command("manual")
    original = plugin._tdp_backend.observe

    def observe_and_invalidate():
        observation = original()
        plugin._advance_tdp_generation()
        return observation

    monkeypatch.setattr(
        plugin._tdp_backend,
        "observe",
        observe_and_invalidate,
    )
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(command)
    assert result.detail == "stale-generation"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_named_firmware_mode_does_not_write_rails(plugin):
    plugin._device = replace(plugin._device, firmware_modes=True)
    plugin._settings["firmware_mode"] = "performance"
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("firmware-mode")
    )
    assert plugin._tdp_backend.set_levels_calls == 0
    assert result.detail == "firmware-mode:performance"
    assert plugin._tdp_history[-1]["action"] == "profile"
    assert plugin._tdp_history[-1]["firmware_mode"] == "performance"


def test_rejected_firmware_mode_is_reported_and_not_persisted(
    plugin,
    monkeypatch,
):
    plugin._device = replace(plugin._device, firmware_modes=True)
    monkeypatch.setattr(
        plugin._tdp_backend,
        "set_profile",
        lambda mode: False,
    )
    state = asyncio.run(
        plugin.set_tdp_firmware_mode("performance")
    )
    assert state["firmware_mode"] == "custom"
    assert state["ownership"]["status"] == "rejected"
    assert state["ownership"]["reason"] == "firmware_mode_rejected"


def _reset_guard_memory(plugin):
    plugin._tdp_reconcile_memory = ReconcileMemory()


def test_guard_ignores_one_shot_spike(plugin):
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_backend._levels["pl1"] = 15
    plugin._tdp_guard_tick(now=10.75)
    assert plugin._tdp_backend.set_levels_calls == 0


def test_guard_corrects_confirmed_drift_without_mutating_profile(plugin):
    plugin._tdp_profiles.set_pl1("global", 15)
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_backend._levels["pl1"] == 15
    assert plugin._tdp_profiles.effective(None)["pl1"] == 15


def test_guard_keeps_global_and_game_profiles_independent(plugin):
    plugin._tdp_profiles.set_pl1("global", 18)
    plugin._tdp_profiles.create_game_from_global("42")
    plugin._tdp_profiles.set_pl1("game", 25, appid="42")

    plugin._current_appid = "42"
    plugin._execute_tdp_command(plugin._capture_tdp_command("game"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    assert plugin._tdp_backend._levels["pl1"] == 25
    assert plugin._tdp_profiles.effective("42")["pl1"] == 25
    assert plugin._tdp_profiles.effective(None)["pl1"] == 18

    plugin._current_appid = None
    plugin._advance_tdp_generation()
    plugin._execute_tdp_command(plugin._capture_tdp_command("global"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=20.0)
    plugin._tdp_guard_tick(now=20.75)
    assert plugin._tdp_backend._levels["pl1"] == 18
    assert plugin._tdp_profiles.effective(None)["pl1"] == 18
    assert plugin._tdp_profiles.effective("42")["pl1"] == 25


def test_guard_respects_follow_global_without_losing_stored_game_value(plugin):
    plugin._tdp_profiles.set_pl1("global", 22)
    plugin._tdp_profiles.create_game_from_global("42")
    plugin._tdp_profiles.set_pl1("game", 12, appid="42")
    plugin._tdp_profiles.set_follow_global("42", True)
    plugin._current_appid = "42"

    plugin._execute_tdp_command(plugin._capture_tdp_command("follow-global"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)

    assert plugin._tdp_backend._levels["pl1"] == 22
    assert plugin._tdp_profiles.effective("42")["pl1"] == 22
    assert plugin._tdp_profiles.effective(None)["pl1"] == 22
    plugin._tdp_profiles.set_follow_global("42", False)
    assert plugin._tdp_profiles.effective("42")["pl1"] == 12


def test_guard_does_nothing_with_control_off(plugin):
    plugin._settings["tdp_control_enabled"] = False
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=11.0)
    assert plugin._tdp_backend.set_levels_calls == 0


def test_guard_does_not_call_full_reapply(plugin, monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin,
        "_reapply_all",
        lambda *a, **k: calls.append(True),
    )
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    assert calls == []


def test_guard_tick_does_not_change_generation(plugin):
    generation = plugin._tdp_generation
    plugin._tdp_guard_tick(now=10.0)
    assert plugin._tdp_generation == generation


def test_guard_drops_stale_observation_before_writing(plugin, monkeypatch):
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=10.0)
    original = plugin._tdp_backend.observe

    def observe_and_invalidate():
        observation = original()
        plugin._advance_tdp_generation()
        return observation

    monkeypatch.setattr(
        plugin._tdp_backend,
        "observe",
        observe_and_invalidate,
    )
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_guard_tick(now=10.75)
    assert plugin._tdp_backend.set_levels_calls == 0


def test_write_only_guard_drops_stale_generation(plugin):
    class InvalidatingWriteOnly(FakeBackend):
        readback = False

        def observe(self):
            plugin._advance_tdp_generation()
            return TdpObservation(readable=False)

        def set_levels(self, pl1, pl2, pl3, ac):
            self.set_levels_calls += 1
            return TdpResult(pl1, None, True, "")

    plugin._tdp_backend = InvalidatingWriteOnly()
    plugin._tdp_reconcile_memory = ReconcileMemory()
    plugin._tdp_guard_tick(now=0.0)
    assert plugin._tdp_backend.set_levels_calls == 0


def test_guard_delay_respects_minimum_correction_interval(
    plugin,
    monkeypatch,
):
    import main as main_module

    plugin._tdp_reconcile_memory = ReconcileMemory(
        pending_signature=(("fake", "pl1", 30, 15),),
        pending_since=99.0,
        last_write_at=99.0,
    )
    monkeypatch.setattr(main_module.time, "monotonic", lambda: 100.0)
    assert plugin._tdp_guard_delay() == 1.0


def test_write_only_guard_uses_backend_heartbeat(plugin):
    class WriteOnly(FakeBackend):
        readback = False
        guard_interval_s = 15.0
        heartbeat_s = 30.0

        def observe(self):
            return TdpObservation(readable=False)

        def set_levels(self, pl1, pl2, pl3, ac):
            self.set_levels_calls += 1
            return TdpResult(pl1, None, True, "")

    plugin._tdp_backend = WriteOnly()
    plugin._tdp_observation = TdpObservation(readable=False)
    plugin._tdp_reconcile_memory = ReconcileMemory()
    plugin._tdp_guard_tick(now=0.0)
    plugin._tdp_guard_tick(now=15.0)
    plugin._tdp_guard_tick(now=29.9)
    plugin._tdp_guard_tick(now=30.0)
    assert plugin._tdp_backend.set_levels_calls == 2


def test_report_contains_tdp_transition_history(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(
        main_module.report_collector,
        "tail_logs",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        main_module.report_collector,
        "sysfs_snapshot",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        main_module.report_collector,
        "kernel_logs",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        main_module.report_collector,
        "build_bundle",
        lambda **kwargs: kwargs,
    )
    plugin._execute_tdp_command(
        plugin._capture_tdp_command("report-test")
    )
    plugin._powerstation_detector.tdp_active = lambda: True
    bundle = asyncio.run(
        plugin._build_report_bundle(
            ["tdp"],
            "test",
            "/home/deck",
            "handheld",
            {
                "display": {
                    "brightness": {
                        "subscribe_available": False,
                        "set_available": True,
                    },
                },
            },
        )
    )
    history = bundle["state"]["tdp_diagnostics"]["history"]
    assert history
    last = history[-1]
    assert {
        "action",
        "scope",
        "write",
        "requested",
        "target",
        "target_reasons",
        "observation",
        "status",
    } <= last.keys()
    diagnostics = bundle["state"]["tdp_diagnostics"]
    assert diagnostics["backend_descriptor"] == plugin._tdp_backend_diagnostics()
    assert bundle["state"]["tdp_conflict"]["powerstation_active"] is True
    display = bundle["state"]["display_diagnostics"]
    assert display["frontend"] == {
        "brightness": {
            "subscribe_available": False,
            "set_available": True,
        },
    }
    assert {"supported", "probe_detail", "wayland_display", "last_apply"} <= (
        display["backend"].keys()
    )


def test_backend_diagnostics_explain_selection_without_personal_identifiers(plugin):
    plugin._tdp_backend.probe_trace = ({
        "candidate": "fake",
        "backend": "fake",
        "supported": True,
    },)

    descriptor = plugin._tdp_backend_diagnostics()

    assert descriptor["device_key"] == plugin._device.key
    assert descriptor["generic"] is plugin._device.is_generic
    assert descriptor["backend"] == "fake"
    assert descriptor["supported"] is True
    assert descriptor["readback"] is True
    assert descriptor["rails"] == ["pl1", "pl2", "pl3"]
    assert descriptor["guard_interval_s"] == 2.0
    assert descriptor["read_tolerance_w"] == 0
    assert descriptor["limits"]["default"] == 15
    assert descriptor["level_limits"]["pl1"]["max"] == 35
    assert descriptor["probe_trace"][0]["candidate"] == "fake"
    assert descriptor["errors"] == {}
    encoded = json.dumps(descriptor).lower()
    for forbidden in ("appid", "title", "hostname", "serial", "uuid", "/home/"):
        assert forbidden not in encoded


def test_backend_diagnostics_are_logged_once_as_compact_json(plugin):
    plugin._test_logs["info"].clear()

    plugin._log_tdp_backend_diagnostics()

    assert len(plugin._test_logs["info"]) == 1
    fmt, encoded = plugin._test_logs["info"][0]
    assert fmt == "TDP backend %s"
    assert json.loads(encoded)["backend"] == "fake"
    assert "\n" not in encoded


def test_unsupported_backend_diagnostics_use_warning(plugin):
    plugin._tdp_backend.supported = False
    plugin._test_logs["warning"].clear()

    plugin._log_tdp_backend_diagnostics()

    assert plugin._test_logs["warning"][0][0] == "TDP backend %s"


def test_backend_diagnostics_survive_broken_live_limits(plugin, monkeypatch):
    monkeypatch.setattr(
        plugin._tdp_backend,
        "get_limits",
        lambda: (_ for _ in ()).throw(OSError("unreadable")),
    )
    plugin._test_logs["warning"].clear()

    descriptor = plugin._tdp_backend_diagnostics()
    plugin._log_tdp_backend_diagnostics()

    assert descriptor["limits_source"] == "profile_fallback"
    assert descriptor["limits"]["default"] == plugin._device.tdp_default
    assert descriptor["errors"]["limits"] == "OSError"
    assert plugin._test_logs["warning"][0][0] == "TDP backend %s"


def test_transition_records_action_scope_and_write_result(plugin):
    plugin._test_logs["info"].clear()

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    event = plugin._tdp_history[-1]
    assert event["action"] == "apply"
    assert event["scope"] == "global"
    assert event["control_enabled"] is True
    assert event["on_ac"] is True
    assert event["firmware_mode"] == "custom"
    assert event["write"] == {
        "ok": True,
        "applied": event["target"]["pl1"],
        "detail": "",
    }
    assert event["target_reasons"]["pl2"] == "live_min"
    assert "appid" not in json.dumps(event).lower()
    fmt, encoded = plugin._test_logs["info"][-1]
    assert fmt == "TDP transition %s"
    assert json.loads(encoded)["action"] == "apply"


def test_disabling_control_records_handoff_without_writing(plugin, monkeypatch):
    plugin._tdp_backend.set_levels_calls = 0

    def handoff():
        plugin._tdp_backend._levels["pl1"] = 20

    monkeypatch.setattr(plugin, "_restore_hhd_tdp", handoff)
    asyncio.run(plugin.set_tdp_control_enabled(False))

    event = plugin._tdp_history[-1]
    assert event["reason"] == "control-disabled"
    assert event["action"] == "release"
    assert event["control_enabled"] is False
    assert event["write"] is None
    assert event["observation"]["surfaces"]["fake"]["pl1"]["applied"] == 20
    assert plugin._tdp_backend.set_levels_calls == 0


def test_stable_guard_does_not_add_history_or_logs(plugin):
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    history_size = len(plugin._tdp_history)
    plugin._test_logs["info"].clear()

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=12.0)

    assert len(plugin._tdp_history) == history_size
    assert plugin._test_logs["info"] == []


def test_rejected_write_warns_and_later_recovery_is_logged(plugin, monkeypatch):
    original = plugin._tdp_backend.set_levels
    monkeypatch.setattr(
        plugin._tdp_backend,
        "set_levels",
        lambda pl1, pl2, pl3, ac: TdpResult(pl1, 15, False, "busy"),
    )

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    rejected = plugin._tdp_history[-1]
    assert rejected["write"]["ok"] is False
    assert rejected["status"] == "settling"
    assert plugin._test_logs["warning"][-1][0] == "TDP transition %s"

    monkeypatch.setattr(plugin._tdp_backend, "set_levels", original)
    plugin._execute_tdp_command(plugin._capture_tdp_command("retry"))

    recovered = plugin._tdp_history[-1]
    assert recovered["write"]["ok"] is True
    assert recovered["status"] in {"in_sync", "constrained"}
    assert plugin._test_logs["info"][-1][0] == "TDP transition %s"


def test_follow_global_transition_uses_scope_without_appid(plugin):
    plugin._tdp_profiles.create_game_from_global("42")
    plugin._tdp_profiles.set_follow_global("42", True)
    plugin._current_appid = "42"

    plugin._execute_tdp_command(plugin._capture_tdp_command("follow-global"))

    event = plugin._tdp_history[-1]
    assert event["scope"] == "game_follow_global"
    assert "appid" not in json.dumps(event).lower()


def test_asus_steam_profile_drift_is_recovered_under_four_seconds(plugin):
    plugin._tdp_backend.set_surface(
        "legacy",
        pl1=15,
        pl2=15,
        pl3=15,
    )
    plugin._tdp_profiles.set_pl1("global", 10)
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    _reset_guard_memory(plugin)
    plugin._tdp_backend.set_surface(
        "armoury",
        pl1=30,
        pl2=42,
        pl3=49,
    )
    plugin._tdp_backend.set_surface(
        "legacy",
        pl1=30,
        pl2=42,
        pl3=49,
    )
    plugin._tdp_guard_tick(now=100.0)
    plugin._tdp_guard_tick(now=100.75)
    assert plugin._tdp_backend.surface("armoury") == {
        "pl1": 10,
        "pl2": 15,
        "pl3": 15,
    }
    assert plugin._tdp_backend.surface("legacy") == {
        "pl1": 10,
        "pl2": 15,
        "pl3": 15,
    }
    assert plugin._tdp_profiles.effective(None)["pl1"] == 10


def test_game_change_invalidates_queued_old_command(plugin):
    plugin._current_appid = "old"
    old = plugin._capture_tdp_command("old-game")
    plugin._current_appid = "new"
    plugin._tdp_profiles.create_game_from_global("new")
    plugin._tdp_profiles.set_pl1("game", 20, appid="new")
    plugin._capture_tdp_command("new-game")
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(old)
    assert result.detail == "stale-generation"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_ac_change_invalidates_queued_old_command(plugin):
    old = plugin._capture_tdp_command("ac", on_ac=True)
    plugin._capture_tdp_command("battery", on_ac=False)
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(old)
    assert result.detail == "stale-generation"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_firmware_mode_invalidates_queued_custom_command(plugin):
    old = plugin._capture_tdp_command("custom")
    plugin._device = replace(plugin._device, firmware_modes=True)
    plugin._settings["firmware_mode"] = "performance"
    plugin._capture_tdp_command("firmware-mode")
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._execute_tdp_command(old)
    assert result.detail == "stale-generation"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_guard_only_touches_tdp(plugin, monkeypatch):
    calls = []
    for name in (
        "_apply_charge_limit",
        "_apply_cpu",
        "_apply_gpu_clock",
        "_reapply_fans",
        "_reapply_color",
    ):
        monkeypatch.setattr(
            plugin,
            name,
            lambda name=name: calls.append(name),
        )
    plugin._tdp_backend._levels["pl1"] = 30
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    assert calls == []
    assert plugin._tdp_backend.set_levels_calls == 1
