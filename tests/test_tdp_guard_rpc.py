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
    auto_tdp_safe = True
    name = "fake"
    low_battery_hold_strategy = "primary"

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


class FakeLowBatteryHoldBackend:
    supported = True
    low_battery_hold_capable = True
    low_battery_hold_strategy = "legion-go-s-83n6"
    name = "ryzenadj-low-battery-hold"
    safety_locked = False

    def __init__(self):
        self.calls = []
        self.active = False
        self.releases = 0
        self.release_ok = True

    def low_battery_level_limits(self, maximum=None):
        maximum = 35 if maximum is None else int(maximum)
        return {
            "pl1": {"min": 5, "max": maximum},
            "pl2": {"min": 15, "max": maximum},
            "pl3": {"min": 20, "max": maximum},
        }

    def hold_levels(self, levels):
        self.calls.append(dict(levels))
        self.active = True
        self.safety_locked = True
        return TdpResult(
            levels["pl1"],
            None,
            True,
            "command accepted (limit readback unavailable)",
        )

    def release_hold(self):
        self.releases += 1
        if not self.release_ok:
            return False
        self.active = False
        self.safety_locked = False
        return True

    def observe_hold(self):
        return TdpObservation(readable=False)

    def diagnostics(self):
        return {"low_battery_hold_active": self.active}


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


def test_anatase_external_owner_blocks_guard_correction(plugin):
    plugin._os_id = "anatase"
    plugin._tdp_external_owner = True
    plugin._tdp_profiles.set_pl1("global", 25)
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)

    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_targets is None
    assert plugin._tdp_status == "unverifiable"
    assert plugin._tdp_reason == "external_owner"


def _set_indeterminate_deck_ppt(plugin, *, with_marker=True):
    from device_profiles import DEVICE_TABLE

    plugin._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "steam_deck_oled"
    )
    plugin._settings["steamdeck_ppt_previous"] = (
        {"slow": 25, "fast": 30} if with_marker else None
    )
    plugin._tdp_backend.configured_tdp_state = lambda _snapshot=None: {
        "status": "unavailable",
        "max_w": None,
        "reason": "bounds_missing",
    }


@pytest.mark.parametrize("with_marker", [True, False])
def test_indeterminate_deck_probe_blocks_command_writes(plugin, with_marker):
    _set_indeterminate_deck_ppt(plugin, with_marker=with_marker)
    plugin._tdp_profiles.set_pl1("global", 25 if with_marker else 15)
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._execute_tdp_command(plugin._capture_tdp_command("startup"))

    assert plugin._tdp_backend.set_levels_calls == 0
    assert result.detail == "steamdeck-ppt-probe-pending"


@pytest.mark.parametrize("with_marker", [True, False])
def test_indeterminate_deck_probe_blocks_guard_writes(plugin, with_marker):
    _set_indeterminate_deck_ppt(plugin, with_marker=with_marker)
    plugin._tdp_profiles.set_pl1("global", 25 if with_marker else 15)
    plugin._tdp_backend.set_levels_calls = 0
    _reset_guard_memory(plugin)

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)

    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_reason == "steamdeck_ppt_probe_pending"
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


def test_legion_manual_ac_probe_attempts_once_then_reports_power_limit(
    plugin,
    monkeypatch,
):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": True)
    plugin._tdp_backend.probe_live_max_on_ac = True
    plugin._tdp_backend.live_max = 15
    plugin._tdp_backend._levels = {"pl1": 15, "pl2": 15, "pl3": 20}
    plugin._tdp_profiles.set_levels("global", 22, 22, 22)
    original_set_levels = plugin._tdp_backend.set_levels

    def reject_above_live_max(pl1, pl2, pl3, ac):
        original_set_levels(pl1, pl2, pl3, ac)
        return TdpResult(
            pl1,
            15,
            False,
            "write not confirmed: fake/pl1=15; rollback confirmed",
            "target_not_applied",
        )

    monkeypatch.setattr(plugin._tdp_backend, "set_levels", reject_above_live_max)
    plugin._tdp_backend.set_levels_calls = 0

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_targets.requested == {"pl1": 22, "pl2": 22, "pl3": 22}
    assert plugin._tdp_targets.target == {"pl1": 22, "pl2": 22, "pl3": 22}
    assert (plugin._tdp_status, plugin._tdp_reason) == (
        "constrained",
        "power_source_limit",
    )

    for now in (10.0, 10.75, 12.0, 40.0):
        plugin._tdp_guard_tick(now=now)

    assert plugin._tdp_backend.set_levels_calls == 1


def test_legion_live_max_probe_is_not_used_for_battery_or_auto_tdp(plugin):
    plugin._tdp_backend.probe_live_max_on_ac = True
    manual_ac = plugin._capture_tdp_command("manual", on_ac=True)

    assert plugin._probe_tdp_live_max(manual_ac) is True
    assert plugin._probe_tdp_live_max(
        replace(manual_ac, on_ac=False),
    ) is False
    assert plugin._probe_tdp_live_max(
        replace(manual_ac, auto_tdp=True),
    ) is False


def test_legion_power_limit_suppresses_scheduled_ac_settle_retries(
    plugin,
    monkeypatch,
):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": True)
    monkeypatch.setattr(plugin, "_offload", lambda callback: callback())
    plugin._tdp_backend.probe_live_max_on_ac = True
    plugin._tdp_backend.live_max = 15
    plugin._tdp_backend._levels = {"pl1": 15, "pl2": 15, "pl3": 20}
    plugin._tdp_profiles.set_levels("global", 22, 22, 22)
    original_set_levels = plugin._tdp_backend.set_levels

    def reject_above_live_max(pl1, pl2, pl3, ac):
        original_set_levels(pl1, pl2, pl3, ac)
        return TdpResult(
            pl1,
            15,
            False,
            "write not confirmed: fake/pl1=15; rollback confirmed",
            "target_not_applied",
        )

    monkeypatch.setattr(plugin._tdp_backend, "set_levels", reject_above_live_max)
    plugin._tdp_backend.set_levels_calls = 0
    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))
    generation = plugin._tdp_generation

    plugin._reassert_tdp_only(on_ac=True)
    plugin._reassert_tdp_only(on_ac=True)

    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_generation == generation
    assert (plugin._tdp_status, plugin._tdp_reason) == (
        "constrained",
        "power_source_limit",
    )


def test_legion_probe_keeps_backoff_for_platform_profile_failure(
    plugin,
    monkeypatch,
):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": True)
    plugin._tdp_backend.probe_live_max_on_ac = True
    plugin._tdp_backend.live_max = 15
    plugin._tdp_profiles.set_levels("global", 22, 22, 22)
    original_set_levels = plugin._tdp_backend.set_levels

    def fail_platform_profile(pl1, pl2, pl3, ac):
        original_set_levels(pl1, pl2, pl3, ac)
        return TdpResult(
            pl1,
            15,
            False,
            "write not confirmed: platform-profile; rollback confirmed",
        )

    monkeypatch.setattr(
        plugin._tdp_backend,
        "set_levels",
        fail_platform_profile,
    )

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    assert (plugin._tdp_status, plugin._tdp_reason) == (
        "settling",
        "write_rejected",
    )
    assert plugin._tdp_reconcile_memory.failures == 1


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


def test_named_firmware_mode_releases_active_sidecar_before_applying_profile(
    plugin,
    monkeypatch,
):
    plugin._device = replace(plugin._device, firmware_modes=True)
    plugin._settings["firmware_mode"] = "performance"
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    plugin._low_battery_hold_backend = sidecar
    order = []
    original_release = sidecar.release_hold

    monkeypatch.setattr(
        sidecar,
        "release_hold",
        lambda: order.append("release") or original_release(),
    )
    monkeypatch.setattr(
        plugin._tdp_backend,
        "set_profile",
        lambda mode: order.append(f"profile:{mode}") or True,
    )

    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("firmware-mode")
    )

    assert result.ok is True
    assert order == ["release", "profile:performance"]


def test_named_firmware_mode_stops_when_active_sidecar_cannot_release(plugin):
    plugin._device = replace(plugin._device, firmware_modes=True)
    plugin._settings["firmware_mode"] = "performance"
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    sidecar.release_ok = False
    plugin._low_battery_hold_backend = sidecar

    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("firmware-mode")
    )

    assert result.ok is False
    assert plugin._tdp_backend._profile == "custom"
    assert plugin._tdp_reason == "low_battery_hold_restore_failed"


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


def _enable_auto_session(plugin, setpoint=5):
    plugin._set_current_appid("42")
    plugin._tdp_profiles.set_auto_config("global", 40, setpoint)
    plugin._tdp_profiles.set_auto_tdp("global", True)
    plugin._ensure_auto_session(on_ac=True)


def test_guard_does_not_reconcile_auto_setpoint_while_ui_is_active(plugin):
    _enable_auto_session(plugin)
    plugin._tdp_backend._levels = {"pl1": 7, "pl2": 15, "pl3": 20}
    asyncio.run(plugin.set_ui_active(True))
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)

    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_backend._levels["pl1"] == 15


def test_guard_does_not_reconcile_auto_setpoint_while_steam_has_focus(plugin):
    _enable_auto_session(plugin)
    plugin._tdp_backend._levels = {"pl1": 5, "pl2": 5, "pl3": 5}
    queued = plugin._capture_tdp_command("settle-retry")
    plugin._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    plugin._gamescope_stats.start = lambda: None
    plugin._gamescope_stats.read = lambda: {
        "fps": None,
        "focus": "steam",
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }

    asyncio.run(plugin._auto_tick())
    plugin._tdp_backend.set_levels_calls = 0
    stale = plugin._execute_tdp_command(queued)
    lifecycle = plugin._execute_tdp_command(
        plugin._capture_tdp_command("lifecycle")
    )
    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)

    assert stale.detail == "stale-generation"
    assert lifecycle.detail == "auto-ui-active"
    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_backend._levels["pl1"] == 15


def test_focus_floor_repairs_drift_on_a_secondary_surface(plugin):
    _enable_auto_session(plugin)
    plugin._tdp_backend._levels = {"pl1": 5, "pl2": 5, "pl3": 5}
    plugin._tdp_backend._legacy_levels = {"pl1": 5, "pl2": 5, "pl3": 5}
    plugin._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    plugin._gamescope_stats.start = lambda: None
    plugin._gamescope_stats.read = lambda: {
        "fps": None,
        "focus": "steam",
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }

    asyncio.run(plugin._auto_tick())
    plugin._tdp_backend._legacy_levels["pl2"] = 14
    plugin._tdp_backend.set_levels_calls = 0
    asyncio.run(plugin._auto_tick())

    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_backend._legacy_levels == {
        "pl1": 15,
        "pl2": 15,
        "pl3": 15,
    }


def test_auto_guard_rechecks_power_source_after_observation(plugin, monkeypatch):
    import main as main_module

    power = {"ac": True}
    monkeypatch.setattr(
        main_module,
        "read_on_ac",
        lambda root="/": power["ac"],
    )
    _enable_auto_session(plugin, setpoint=10)
    plugin._tdp_backend._levels = {"pl1": 20, "pl2": 20, "pl3": 20}
    plugin._tdp_guard_tick(now=10.0)
    original_observe = plugin._tdp_backend.observe

    def observe_then_unplug():
        observation = original_observe()
        power["ac"] = False
        return observation

    monkeypatch.setattr(plugin._tdp_backend, "observe", observe_then_unplug)
    calls = []
    plugin._tdp_backend.apply_auto_targets = lambda targets, ac: calls.append(
        (dict(targets), ac)
    ) or TdpResult(targets["pl1"], targets["pl1"], True, "")

    plugin._tdp_guard_tick(now=10.75)

    assert calls == []


def test_queued_settle_retry_does_not_write_auto_setpoint_during_ui_pause(
    plugin,
):
    _enable_auto_session(plugin)
    plugin._tdp_backend._levels = {"pl1": 7, "pl2": 15, "pl3": 20}
    asyncio.run(plugin.set_ui_active(True))
    command = plugin._capture_tdp_command("settle-retry")
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._execute_tdp_command(command)

    assert result.detail == "auto-ui-active"
    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_backend._levels["pl1"] == 15


def test_grid_guard_keeps_physical_hold_while_qam_is_open(plugin):
    plugin._tdp_profiles.set_auto_tdp("global", True)
    asyncio.run(plugin.set_ui_active(True))
    plugin._tdp_backend._levels = {"pl1": 7, "pl2": 15, "pl3": 20}
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=10.75)
    plugin._tdp_guard_tick(now=12.0)

    assert plugin._auto_controller is None
    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_backend._levels["pl1"] == 7


def test_grid_queued_settle_retry_is_blocked_when_qam_opens(plugin):
    plugin._tdp_profiles.set_auto_tdp("global", True)
    command = plugin._capture_tdp_command("settle-retry")
    asyncio.run(plugin.set_ui_active(True))
    plugin._tdp_backend._levels = {"pl1": 7, "pl2": 15, "pl3": 20}
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._execute_tdp_command(command)

    assert result.detail == "auto-ui-active"
    assert plugin._auto_controller is None
    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_backend._levels["pl1"] == 7


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


def test_game_authoritative_reassert_rewrites_matching_persisted_target(plugin):
    plugin._tdp_backend.authoritative_reassert_s = 15.0
    plugin._tdp_profiles.set_pl1("global", 13)
    plugin._current_appid = "42"
    plugin._execute_tdp_command(plugin._capture_tdp_command("game"))
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=100.0)

    plugin._tdp_guard_tick(now=114.9)
    plugin._tdp_guard_tick(now=115.0)

    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_backend._levels == {"pl1": 13, "pl2": 15, "pl3": 15}
    assert plugin._tdp_profiles.effective("42")["pl1"] == 13
    assert plugin._tdp_history[-1]["action"] == "reassert"
    assert plugin._tdp_history[-1]["write"]["ok"] is True


def test_authoritative_reassert_is_idle_without_running_game(plugin):
    plugin._tdp_backend.authoritative_reassert_s = 15.0
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=100.0)
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=115.0)

    assert plugin._tdp_backend.set_levels_calls == 0


def test_low_battery_hold_reasserts_the_selected_global_tdp(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 20, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 19, 23, 27)
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=100.0)

    plugin._tdp_guard_tick(now=114.9)
    plugin._tdp_guard_tick(now=115.0)

    assert plugin._tdp_backend.set_levels_calls == 1
    assert plugin._tdp_backend._levels == {"pl1": 19, "pl2": 23, "pl3": 27}
    assert plugin._tdp_profiles.effective(None)["pl1"] == 19


def test_primary_hold_is_not_verified_from_a_stale_in_sync_status(
    plugin,
    monkeypatch,
):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 20, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 20, 23, 27)
    plugin._execute_tdp_command(plugin._capture_tdp_command("initial"))
    assert plugin._tdp_status == "in_sync"
    plugin._tdp_backend._levels = {"pl1": 15, "pl2": 15, "pl3": 20}

    state = plugin._tdp_state(plugin._tdp_backend.observe())

    assert state["low_battery_hold"]["active"] is False
    assert state["low_battery_hold"]["verified"] is False


def test_low_battery_hold_off_does_not_read_battery_or_add_writes(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: (_ for _ in ()).throw(AssertionError("battery read while disabled")),
    )
    plugin._settings["low_battery_tdp_hold"] = False
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=100.0)
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=115.0)

    assert plugin._tdp_backend.set_levels_calls == 0


def test_low_battery_hold_setting_is_persisted_and_returned(plugin, monkeypatch):
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 42, "status": "Discharging"},
    )

    state = asyncio.run(plugin.set_low_battery_tdp_hold(True))

    assert plugin._settings["low_battery_tdp_hold"] is True
    assert state["low_battery_hold"] == {
        "available": True,
        "enabled": True,
        "active": False,
        "verified": False,
        "status": "inactive",
        "applied_w": None,
        "reason": "on_ac",
    }


def test_legion_go_s_hold_uses_requested_rails_without_the_firmware_cap(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 19, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 19, 23, 27)
    plugin._tdp_backend.live_max = 15
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=10.0)
    plugin._tdp_guard_tick(now=11.9)
    plugin._tdp_guard_tick(now=12.0)

    assert sidecar.calls == [
        {"pl1": 19, "pl2": 23, "pl3": 27},
        {"pl1": 19, "pl2": 23, "pl3": 27},
    ]
    assert plugin._tdp_backend.set_levels_calls == 0


def test_legion_go_s_manual_change_uses_the_hold_route_immediately(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 18, 22, 26)
    plugin._tdp_backend.live_max = 15
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("manual")
    )

    assert result.ok is True
    assert sidecar.calls == [{"pl1": 18, "pl2": 22, "pl3": 26}]
    assert plugin._tdp_backend.set_levels_calls == 0


def test_legion_go_s_hold_respects_boost_rail_floors(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    monkeypatch.setattr(
        plugin._tdp_backend,
        "level_limits",
        lambda: {
            "pl1": {"min": 5, "max": 35},
            "pl2": {"min": 15, "max": 35},
            "pl3": {"min": 20, "max": 35},
        },
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 5, 5, 5)

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    assert sidecar.calls == [{"pl1": 5, "pl2": 15, "pl3": 20}]


def test_legion_go_s_hold_builds_all_rails_when_primary_only_has_pl1(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    plugin._tdp_backend.supports_levels = False
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 5, 5, 5)

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    assert sidecar.calls == [{"pl1": 5, "pl2": 15, "pl3": 20}]


def test_legion_go_s_hold_honours_the_existing_battery_ceiling_opt_in(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(
        plugin._tdp_backend,
        "get_limits",
        lambda: TdpLimits(min_w=5, default_w=15, max_w=33, max_ac_w=40),
    )
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["unlock_battery_max"] = True
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 38, 38, 38)

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    assert sidecar.calls == [{"pl1": 38, "pl2": 38, "pl3": 38}]


def test_legion_go_s_write_only_hold_is_active_without_claiming_verification(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 19, 23, 27)

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))
    state = plugin._tdp_state(plugin._tdp_observation)

    assert state["low_battery_hold"]["active"] is True
    assert state["low_battery_hold"]["verified"] is False
    assert state["low_battery_hold"]["status"] == "unverified"
    assert state["low_battery_hold"]["applied_w"] is None
    assert state["ownership"]["status"] == "unverifiable"


def test_legion_go_s_ac_reapply_restores_hold_before_using_primary(
    plugin,
    monkeypatch,
):
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Charging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("ac-change", on_ac=True)
    )

    assert result.ok is True
    assert sidecar.releases == 1
    assert plugin._tdp_backend.set_levels_calls == 1


def test_legion_go_s_hold_restores_its_snapshot_when_battery_recovers(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 21, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True

    plugin._tdp_guard_tick(now=10.0)

    assert sidecar.releases == 1
    assert sidecar.active is False


def test_failed_sidecar_restore_blocks_the_primary_guard(plugin, monkeypatch):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    sidecar.release_ok = False
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 21, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=10.0)

    assert sidecar.releases == 1
    assert plugin._tdp_backend.set_levels_calls == 0
    assert plugin._tdp_status == "rejected"
    assert plugin._tdp_reason == "low_battery_hold_restore_failed"
    assert plugin._low_battery_hold_recovery_pending is True


def test_failed_sidecar_restore_is_reported_when_toggle_is_disabled(
    plugin,
    monkeypatch,
):
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    sidecar.release_ok = False
    plugin._low_battery_hold_backend = sidecar
    plugin._settings["low_battery_tdp_hold"] = True

    state = asyncio.run(plugin.set_low_battery_tdp_hold(False))

    assert plugin._settings["low_battery_tdp_hold"] is False
    assert state["supported"] is False
    assert state["low_battery_hold"]["enabled"] is False
    assert state["low_battery_hold"]["active"] is False
    assert state["low_battery_hold"]["status"] == "recovery_pending"
    assert state["low_battery_hold"]["verified"] is False


def test_disabling_sidecar_reapplies_the_primary_backend_after_restore(plugin):
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    plugin._low_battery_hold_backend = sidecar
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_backend.set_levels_calls = 0

    state = asyncio.run(plugin.set_low_battery_tdp_hold(False))

    assert sidecar.releases == 1
    assert plugin._tdp_backend.set_levels_calls == 1
    assert state["low_battery_hold"]["enabled"] is False


def test_emergency_handoff_defers_all_power_writers_until_serial_worker(
    plugin,
    monkeypatch,
):
    sidecar = FakeLowBatteryHoldBackend()
    sidecar.active = True
    sidecar.safety_locked = True
    plugin._low_battery_hold_backend = sidecar
    handoffs = []
    monkeypatch.setattr(
        plugin,
        "_restore_hhd_tdp",
        lambda preserve_ownership=False: handoffs.append(preserve_ownership) or True,
    )

    assert plugin._restore_power_handoff(preserve_ownership=True) is None
    assert sidecar.releases == 0
    assert handoffs == []


def test_emergency_handoff_preserves_active_backend_auto_ownership(
    plugin, monkeypatch
):
    releases = []
    plugin._tdp_backend.owns_auto_state = True
    monkeypatch.setattr(
        plugin._tdp_backend,
        "release",
        lambda: releases.append(True) or True,
    )

    assert plugin._restore_power_handoff(preserve_ownership=True) is None
    assert releases == []

    assert plugin._restore_power_handoff() is True
    assert releases == [True]


def test_power_draw_does_not_publish_cached_primary_blocking_readback(plugin):
    plugin._tdp_backend.blocking = True
    plugin._tdp_observation = plugin._tdp_backend.observe()

    power = asyncio.run(plugin.get_power_draw())

    assert power["applied"] is None


def test_failed_common_hold_is_never_reported_as_active(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    monkeypatch.setattr(
        plugin._tdp_backend,
        "set_levels",
        lambda pl1, pl2, pl3, ac: TdpResult(pl1, None, False, "rejected"),
    )
    plugin._settings["low_battery_tdp_hold"] = True

    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))
    state = plugin._tdp_state(plugin._tdp_observation)

    assert state["low_battery_hold"]["active"] is False
    assert state["low_battery_hold"]["verified"] is False
    assert state["low_battery_hold"]["status"] == "failed"


@pytest.mark.parametrize("inactive_auto", ("module", "unsafe_backend"))
def test_inactive_auto_intent_does_not_block_low_battery_hold(
    plugin,
    monkeypatch,
    inactive_auto,
):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_auto_tdp("global", True)
    if inactive_auto == "module":
        plugin._settings["disabled_modules"] = ["autoTdp"]
    else:
        plugin._tdp_backend.auto_tdp_safe = False

    decision = plugin._low_battery_hold_decision(on_ac=False)

    assert decision.active is True
    assert decision.reason == "active"


def test_active_auto_control_still_blocks_low_battery_hold(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_auto_tdp("global", True)

    decision = plugin._low_battery_hold_decision(on_ac=False)

    assert decision.active is False
    assert decision.reason == "auto_tdp"


def test_sidecar_rechecks_ac_immediately_before_writing(plugin, monkeypatch):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": True)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    command = plugin._capture_tdp_command("manual", on_ac=False)

    result = plugin._execute_tdp_command(command)

    assert sidecar.calls == []
    assert result.detail == "low-battery-hold-condition-changed"


def test_startup_recovers_an_interrupted_low_battery_hold(plugin, monkeypatch):
    recovered = []
    plugin._low_battery_hold_backend = types.SimpleNamespace(
        safety_locked=True,
        recover_runtime_transaction=lambda: recovered.append(True) or {
            "ok": True,
            "detail": "restored",
        },
    )

    async def ownership_is_free():
        return False

    monkeypatch.setattr(plugin, "_prime_tdp_ownership", ownership_is_free)
    monkeypatch.setattr(plugin, "_recover_tdp_runtime_transaction", lambda: True)

    assert asyncio.run(plugin._recover_tdp_startup_state()) is True
    assert recovered == [True]


def test_anatase_defers_sidecar_recovery_while_hhd_owns_tdp(plugin, monkeypatch):
    recovered = []
    plugin._os_id = "anatase"
    plugin._low_battery_hold_backend = types.SimpleNamespace(
        safety_locked=True,
        recover_runtime_transaction=lambda: recovered.append(True) or {
            "ok": True,
            "detail": "restored",
        },
    )
    plugin._low_battery_hold_recovery_pending = True

    async def ownership_is_external():
        plugin._tdp_external_owner = True
        return True

    monkeypatch.setattr(plugin, "_prime_tdp_ownership", ownership_is_external)

    assert asyncio.run(plugin._recover_tdp_startup_state()) is False
    assert recovered == []
    assert plugin._low_battery_hold_recovery_pending is True
    assert plugin._tdp_supported() is False


def test_string_false_does_not_enable_low_battery_hold(plugin, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: (_ for _ in ()).throw(AssertionError("invalid bool read battery")),
    )
    plugin._settings["low_battery_tdp_hold"] = "false"
    plugin._tdp_backend.set_levels_calls = 0

    plugin._tdp_guard_tick(now=15.0)

    assert plugin._tdp_backend.set_levels_calls == 0


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


def test_guard_delay_wakes_when_game_authoritative_reassert_is_due(
    plugin,
    monkeypatch,
):
    import main as main_module

    plugin._tdp_backend.authoritative_reassert_s = 15.0
    plugin._current_appid = "42"
    plugin._tdp_reconcile_memory = ReconcileMemory(last_write_at=100.0)
    monkeypatch.setattr(main_module.time, "monotonic", lambda: 114.0)

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

    def hud_state():
        return {
            "capability": "inactive",
            "applyStatus": "pending",
            "conflict": None,
            "model": {},
            "values": {},
        }

    monkeypatch.setattr(plugin, "_hud_state", hud_state)
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
                "qam": {
                    "rendered_count": 8,
                    "rendered_unique_count": 7,
                },
                "steam_performance": {
                    "schema": 1,
                    "current": {
                        "profile": {
                            "status": "request_failed",
                            "running_game_id": "42",
                        },
                    },
                    "events": [],
                },
                "report_kind": "feature",
            },
        )
    )
    assert bundle["kind"] == "feature"
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
    cpu_gpu = bundle["state"]["cpu_gpu_diagnostics"]
    assert set(cpu_gpu) == {"cpu", "gpu", "steamdeck_ppt", "reapply"}
    assert cpu_gpu["cpu"]["supported"] is False
    assert cpu_gpu["gpu"]["supported"] is False
    assert bundle["state"]["lifecycle_diagnostics"] == plugin._lifecycle.diagnostics()
    assert bundle["state"]["controller_diagnostics"] == (
        plugin._controller_backend.diagnostics()
    )
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
    assert bundle["state"]["launch"]["frontend"]["qam"] == {
        "rendered_count": 8,
        "rendered_unique_count": 7,
    }
    assert bundle["state"]["launch"]["frontend"]["steam_performance"] == {
        "schema": 1,
        "current": {
            "profile": {
                "status": "request_failed",
                "running_game_id": "42",
            },
        },
        "events": [],
    }
    hud = bundle["state"]["hud_diagnostics"]
    assert hud["capability"] == "inactive"


def test_report_collects_autotdp_diagnostics_for_an_unrelated_category(
    plugin, monkeypatch
):
    import main as main_module

    monkeypatch.setattr(main_module, "_monotonic", lambda: 100.0)
    monkeypatch.setattr(main_module.report_collector, "tail_logs", lambda *a, **k: [])
    monkeypatch.setattr(main_module.report_collector, "sysfs_snapshot", lambda *a, **k: {})
    monkeypatch.setattr(main_module.report_collector, "kernel_logs", lambda *a, **k: {})
    monkeypatch.setattr(
        main_module.report_collector,
        "build_bundle",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(plugin, "_hud_state", lambda: {})

    plugin._set_current_appid("42")
    plugin._tdp_profiles.set_auto_config("game", 60, 15, appid="42")
    plugin._tdp_profiles.set_auto_tdp("game", True, appid="42")
    controller, _created = plugin._ensure_auto_session(on_ac=True)
    decision = controller.step(fps=60, signal_reason="ok", gpu_busy=55)
    plugin._record_auto_status(
        decision,
        {"age_s": 0.2, "focus": "42"},
    )
    plugin._gamescope_stats._apply_line("fps=58")
    plugin._gamescope_stats._apply_line("focus=42")
    asyncio.run(plugin.set_ui_active(True))
    plugin._auto_stats_reader_active = True
    plugin._auto_apply_blocked = True
    plugin._auto_apply_attempts = 2
    plugin._auto_apply_retry_at = 105.0
    for _ in range(6):
        plugin._auto_learning.record("42", 60, True, 15, stable=True)

    bundle = asyncio.run(
        plugin._build_report_bundle(
            ["fans"],
            "The fan page is slow",
            "/home/deck",
            "handheld",
            {},
        )
    )

    auto = bundle["state"]["auto_tdp"]
    assert bundle["categories"] == ["fans"]
    assert auto["schema"] == 1
    assert auto["supported"] is True
    assert auto["enabled"] is True
    assert auto["active"] is True
    assert auto["target_fps"] == 60
    assert auto["ui"]["active"] is True
    assert auto["ui"]["focus_hold"] is False
    assert auto["apply"]["blocked"] is True
    assert auto["apply"]["attempts"] == 2
    assert auto["apply"]["retry_in_s"] == 5.0
    assert auto["signal"]["reader_requested"] is True
    assert auto["signal"]["focus"] == "game"
    assert auto["learning"]["usable"] is True
    assert auto["last_pre_ui"]["reason"] != "ui_active"
    assert auto["last_pre_ui"]["fps"] == 58
    assert "42" not in json.dumps(auto)


def test_autotdp_diagnostics_do_not_reprobe_backend_readiness(plugin):
    plugin._set_current_appid("42")
    plugin._tdp_profiles.set_auto_tdp("game", True, appid="42")
    plugin._ensure_auto_session(on_ac=True)
    calls = 0

    def ready():
        nonlocal calls
        calls += 1
        return True

    plugin._tdp_backend.ready = ready

    diagnostics = plugin._auto_tdp_diagnostics(
        {
            "supports_auto_tdp": True,
            "auto_config": {"enabled": True, "target_fps": 40},
            "auto_limits": {"min": 5, "max": 35, "max_ac": 35},
            "on_ac": True,
        },
        {"auto_tdp": True, "setpoint": 15},
    )

    assert diagnostics["active"] is True
    assert calls == 0


def test_autotdp_diagnostics_include_sanitized_gpu_signal_source(plugin):
    plugin._power_reader.gpu_diagnostics = lambda: {
        "source": "intel_xe_fdinfo",
        "state": "ok",
        "clients": 3,
        "engines": 4,
    }

    diagnostics = plugin._auto_tdp_diagnostics({}, {})

    assert diagnostics["signal"]["gpu_activity"] == {
        "source": "intel_xe_fdinfo",
        "state": "ok",
        "clients": 3,
        "engines": 4,
    }


@pytest.mark.parametrize(
    "on_ac, expected_max",
    [(False, 35), (True, 40)],
)
def test_autotdp_diagnostics_apply_configured_range_to_learning(
    plugin, on_ac, expected_max
):
    plugin._set_current_appid("42")
    plugin._tdp_profiles.set_auto_tdp("game", True, appid="42")
    for _ in range(6):
        plugin._auto_learning.record("42", 60, on_ac, 42, stable=True)

    diagnostics = plugin._auto_tdp_diagnostics(
        {
            "supports_auto_tdp": True,
            "auto_config": {
                "enabled": True,
                "target_fps": 60,
                "min_tdp": 12,
                "max_tdp": 40,
            },
            "auto_limits": {"min": 5, "max": 35, "max_ac": 45},
            "on_ac": on_ac,
        },
        {"auto_tdp": True, "setpoint": 15},
    )

    assert diagnostics["effective_range"] == {"min_w": 12, "max_w": expected_max}
    assert diagnostics["learning"]["candidate_watts"] == expected_max


def test_incomplete_feature_report_keeps_its_kind(plugin, monkeypatch):
    import main as main_module

    async def fail_bundle(*_args, **_kwargs):
        raise RuntimeError("incomplete")

    captured = {}

    def build_bundle(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(plugin, "_build_report_bundle", fail_bundle)
    monkeypatch.setattr(main_module.report_collector, "build_bundle", build_bundle)
    monkeypatch.setattr(
        main_module.report_client,
        "submit",
        lambda *_args, **_kwargs: {"ok": True, "code": "PDC-TEST"},
    )

    result = asyncio.run(plugin.submit_report(
        ["themes"],
        "please add this",
        {"report_kind": "feature"},
    ))

    assert result["ok"] is True
    assert captured["kind"] == "feature"
    assert captured["state"] == {
        "auto_tdp": {"schema": 1, "error": "bundle_incomplete"},
    }


def test_cpu_gpu_diagnostics_allowlist_drops_app_identity(plugin):
    class _MaliciousGpu:
        supported = True
        backend = "fake"

        def diagnostics(self):
            return {
                "backend": "fake",
                "supported": True,
                "range": {"min_mhz": 200, "max_mhz": 2000},
                "applied": {"min_mhz": 300, "max_mhz": 1800},
                "appid": "APPID-SECRET",
                "title": "GAME-TITLE-SECRET",
                "raw_sysfs": "/home/alice/secret",
            }

    plugin._gpu_clock = _MaliciousGpu()
    encoded = json.dumps(plugin._cpu_gpu_diagnostics(), sort_keys=True)
    assert "APPID-SECRET" not in encoded
    assert "GAME-TITLE-SECRET" not in encoded
    assert "/home/alice" not in encoded


def test_cpu_gpu_diagnostics_keeps_deck_ppt_probe_failure_reason(plugin):
    plugin._tdp_backend.diagnostics = lambda: {
        "ppt": {"supported": False, "source": None},
        "ppt_reason": "contradictory_labels",
    }

    deck = plugin._cpu_gpu_diagnostics()["steamdeck_ppt"]

    assert deck["probe_reason"] == "contradictory_labels"
    assert deck["overclock"] == {
        "detected": False,
        "max_w": None,
        "source": None,
        "status": "unsupported",
        "reason": None,
    }


def test_confirmed_resume_is_written_to_plugin_log(plugin):
    wakeup = {"value": 10}
    suspended = {"value": 0.0}
    plugin._lifecycle._read_wakeup = lambda: wakeup["value"]
    plugin._lifecycle._read_suspend = lambda: suspended["value"]
    plugin._lifecycle._read_ac = lambda: True
    plugin._lifecycle.check(now=0.0)
    wakeup["value"] = 11
    suspended["value"] = 2.5

    plugin._lifecycle.check(now=2.0)

    lifecycle_logs = [
        args
        for args in plugin._test_logs["info"]
        if args and args[0] == "Lifecycle transition %s"
    ]
    assert lifecycle_logs
    assert json.loads(lifecycle_logs[-1][1]) == {
        "event": "resume_detected",
        "full_delay_seconds": 4.0,
        "suspend_seconds": 2.5,
        "tdp_settle_retries": 3,
    }


def test_controller_dbus_failure_is_written_to_plugin_log(plugin):
    event = {
        "operation": "reset_default",
        "ok": False,
        "reason": "busctl_exit",
        "returncode": 1,
    }

    plugin._log_controller_event(event)

    assert plugin._test_logs["warning"][-1][0] == "Controller transition %s"
    assert json.loads(plugin._test_logs["warning"][-1][1]) == event


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
    assert descriptor["authoritative_reassert_s"] is None
    assert descriptor["low_battery_hold"] == {
        "strategy": "primary",
        "enabled": False,
        "active": False,
        "verified": False,
        "recovery_pending": False,
        "reason": "disabled",
        "battery_percent": None,
        "sidecar": None,
    }
    assert descriptor["limits"]["default"] == 15
    assert descriptor["level_limits"]["pl1"]["max"] == 35
    assert descriptor["probe_trace"][0]["candidate"] == "fake"
    assert descriptor["errors"] == {}
    encoded = json.dumps(descriptor).lower()
    for forbidden in ("appid", "title", "hostname", "serial", "uuid", "/home/"):
        assert forbidden not in encoded


def test_backend_diagnostics_publish_authoritative_reassert_cadence(plugin):
    plugin._tdp_backend.authoritative_reassert_s = 15.0

    descriptor = plugin._tdp_backend_diagnostics()

    assert descriptor["authoritative_reassert_s"] == 15.0


def test_backend_diagnostics_keep_write_only_sidecar_active_but_unverified(
    plugin,
    monkeypatch,
):
    import main as main_module

    sidecar = FakeLowBatteryHoldBackend()
    plugin._low_battery_hold_backend = sidecar
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    monkeypatch.setattr(
        plugin._battery,
        "read",
        lambda: {"present": True, "percent": 18, "status": "Discharging"},
    )
    plugin._settings["low_battery_tdp_hold"] = True
    plugin._tdp_profiles.set_levels("global", 20, 20, 20)
    plugin._execute_tdp_command(plugin._capture_tdp_command("manual"))

    descriptor = plugin._tdp_backend_diagnostics()

    assert descriptor["low_battery_hold"]["active"] is True
    assert descriptor["low_battery_hold"]["verified"] is False


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


def test_backend_diagnostics_include_selected_rail_floors(plugin):
    plugin._tdp_backend._rail_floors = {"pl2": 15, "pl3": 20}

    descriptor = plugin._tdp_backend_diagnostics()

    assert descriptor.get("rail_floors") == {"pl2": 15, "pl3": 20}


def test_backend_can_cap_boost_rails_to_active_battery_max(plugin):
    plugin._tdp_backend.cap_boost_to_active = True
    plugin._tdp_backend.get_limits = lambda: TdpLimits(
        min_w=5,
        default_w=15,
        max_w=33,
        max_ac_w=40,
    )
    plugin._tdp_backend.level_limits = lambda: {
        "pl1": {"min": 5, "max": 40},
        "pl2": {"min": 15, "max": 40},
        "pl3": {"min": 20, "max": 40},
    }

    command = plugin._capture_tdp_command("battery", on_ac=False)

    assert command.safe_bounds == {
        "pl1": {"min": 5, "max": 33},
        "pl2": {"min": 15, "max": 33},
        "pl3": {"min": 20, "max": 33},
    }


def _use_real_steamdeck_backend(plugin, root, slow, fast):
    from device_profiles import DEVICE_TABLE
    from tdp.steamdeck_hwmon import SteamDeckHwmonBackend

    directory = root / "sys/class/hwmon/hwmon7"
    directory.mkdir(parents=True)
    values = {
        "name": "amdgpu",
        "power1_label": "slowPPT",
        "power1_cap": slow * 1_000_000,
        "power1_cap_min": 0,
        "power1_cap_max": 29_000_000,
        "power2_label": "fastPPT",
        "power2_cap": fast * 1_000_000,
        "power2_cap_min": 0,
        "power2_cap_max": 30_000_000,
    }
    for name, value in values.items():
        (directory / name).write_text(str(value))

    plugin._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "steam_deck_lcd"
    )
    plugin._tdp_backend = SteamDeckHwmonBackend(
        TdpLimits(3, 12, 15, 15),
        "steam_deck_lcd",
        root=str(root),
    )
    plugin._settings["steamdeck_ppt_previous"] = None
    return directory


@pytest.mark.parametrize(
    ("slow_ppt", "fast_ppt", "requested", "expected_target", "ceiling"),
    [
        pytest.param(15, 15, (14, 17), (14, 15), 15, id="stock"),
        pytest.param(25, 30, (25, 29), (25, 25), 25, id="overclocked"),
    ],
)
def test_steamdeck_caps_every_product_rail_to_the_detected_ceiling(
    plugin,
    tmp_path,
    slow_ppt,
    fast_ppt,
    requested,
    expected_target,
    ceiling,
):
    directory = _use_real_steamdeck_backend(plugin, tmp_path, slow_ppt, fast_ppt)
    plugin._tdp_profiles.set_levels("global", requested[0], *requested)

    command = plugin._capture_tdp_command("manual", on_ac=True)
    result = plugin._execute_tdp_command(command)
    state = plugin._tdp_state(plugin._observe_tdp_sync())

    expected_limits = {
        "pl2": {"min": 3, "max": ceiling},
        "pl3": {"min": 3, "max": ceiling},
    }
    requested_levels = dict(zip(("pl2", "pl3"), requested))
    target_levels = dict(zip(("pl2", "pl3"), expected_target))
    assert command.safe_bounds == expected_limits
    assert result.ok is True
    assert plugin._tdp_targets.requested == requested_levels
    assert plugin._tdp_targets.target == target_levels
    assert state["level_limits"] == expected_limits
    assert state["ppt"]["visual_max"] == 30
    for cap_file, watts in zip(("power1_cap", "power2_cap"), expected_target):
        assert (directory / cap_file).read_text().strip() == str(watts * 1_000_000)


def test_confirmed_secondary_rail_floor_is_constrained_without_retry(plugin):
    plugin._tdp_backend._rail_floors = {"pl2": 15, "pl3": 20}
    plugin._tdp_backend.level_limits = lambda: {
        "pl1": {"min": 5, "max": 35},
        "pl2": {"min": 15, "max": 42},
        "pl3": {"min": 20, "max": 49},
    }
    plugin._tdp_backend._levels = {"pl1": 15, "pl2": 15, "pl3": 20}
    plugin._tdp_profiles.set_levels("global", 15, 15, 15)

    result = plugin._execute_tdp_command(
        plugin._capture_tdp_command("manual")
    )

    assert result.ok is True
    assert plugin._tdp_targets.requested == {
        "pl1": 15,
        "pl2": 15,
        "pl3": 15,
    }
    assert plugin._tdp_targets.target == {
        "pl1": 15,
        "pl2": 15,
        "pl3": 20,
    }
    assert plugin._tdp_targets.reasons == {"pl3": "safe_min"}
    assert plugin._tdp_status == "constrained"
    assert plugin._tdp_reconcile_memory.failures == 0
    plugin._tdp_backend.set_levels_calls = 0
    plugin._tdp_guard_tick(now=10.0)
    assert plugin._tdp_backend.set_levels_calls == 0


def test_disabling_control_records_handoff_without_writing(plugin, monkeypatch):
    plugin._tdp_backend.set_levels_calls = 0

    def handoff():
        plugin._tdp_backend._levels["pl1"] = 20
        return True

    monkeypatch.setattr(plugin, "_restore_hhd_tdp", handoff)
    asyncio.run(plugin.set_tdp_control_enabled(False))

    event = plugin._tdp_history[-1]
    assert event["reason"] == "control-disabled"
    assert event["action"] == "release"
    assert event["control_enabled"] is False
    assert event["write"] is None
    assert event["observation"]["surfaces"]["fake"]["pl1"]["applied"] == 20
    assert plugin._tdp_backend.set_levels_calls == 0


def test_disabling_control_reports_pending_release_when_handoff_fails(
    plugin, monkeypatch
):
    monkeypatch.setattr(plugin, "_restore_power_handoff", lambda: False)

    asyncio.run(plugin.set_tdp_control_enabled(False))

    assert plugin._settings["tdp_control_enabled"] is False
    assert plugin._tdp_status == "rejected"
    assert plugin._tdp_reason == "release_failed"
    event = plugin._tdp_history[-1]
    assert event["reason"] == "control-disable-release-failed"
    assert event["status"] == "rejected"


def test_disabling_power_module_reports_pending_release_when_handoff_fails(
    plugin, monkeypatch
):
    monkeypatch.setattr(plugin, "_restore_power_handoff", lambda: False)

    asyncio.run(plugin.set_ui_module("power", True))

    assert plugin._tdp_status == "rejected"
    assert plugin._tdp_reason == "release_failed"
    event = plugin._tdp_history[-1]
    assert event["reason"] == "module-disable-release-failed"
    assert event["status"] == "rejected"


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


def test_auto_command_rechecks_power_source_before_backend_ownership(
    plugin, monkeypatch
):
    import main as main_module

    calls = []
    plugin._tdp_backend.apply_auto_targets = lambda targets, ac: calls.append(
        (dict(targets), ac)
    ) or TdpResult(targets["pl1"], targets["pl1"], True, "")
    plugin._tdp_profiles.set_auto_config("global", 40, 18)
    plugin._tdp_profiles.set_auto_tdp("global", True)
    plugin._ensure_auto_session(on_ac=True)
    command = plugin._capture_tdp_command("auto", on_ac=True)
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)

    result = plugin._execute_tdp_command(command)

    assert result.detail == "stale-power-source"
    assert calls == []


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
