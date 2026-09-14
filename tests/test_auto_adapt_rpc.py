"""RPC-level regression coverage for the G auto-adaptation wiring (seed + dial +
fan auto-apply + learned-band state). Pure logic is unit-tested in
test_tdp_suggest / test_auto_tdp / test_fans_suggest; this locks the glue in main.py.
"""
import asyncio
import importlib
import sys
import threading
import types

import pytest

from gamescope_stats import GamescopeStats
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


class FakeBackend:
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self._applied = None
        self._levels = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 35}}

    def set_levels(self, pl1, pl2, pl3, ac):
        self._applied = pl1
        self._levels = (pl1, pl2, pl3)
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied


class FakeFan:
    """Supported fan backend that records the last applied curve."""
    supported = True
    name = "fake-fan"

    def __init__(self):
        self.applied = None
        self.auto_called = False

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255, "fans": []}

    def apply_curve_all(self, points):
        self.applied = points

    def set_auto(self, points):
        self.auto_called = True

    def restore_auto(self):
        self.auto_called = True


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "decky", fake)
    import tdp.factory as factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    import fans.control as fan_control
    monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


def _feed_tdp_band(p, appid="123"):
    """Telemetry (GPU-only, watts-less → gpu fallback) yielding floor=15, ceil=21."""
    rows = [(12, 99, 700), (15, 96, 700), (18, 88, 900), (21, 80, 700)]
    for pl1, gpu, secs in rows:
        p._telemetry.add_sample(appid, {"pl1": pl1, "gpu_busy": gpu}, dt=secs)


def _feed_temp_band(p, appid="123"):
    """Telemetry temp histogram with >30 min weighted dwell and >8 C spread.

    Feeds realistic 5 s samples; the store decays old dwell (~30 min half-life)
    so weighted dwell tops out below wall-clock — ~60 min of real play clears the
    30-min gate (a single huge-dt sample would just fade itself away).
    """
    for t in (58, 62, 66, 70, 74, 78):
        for _ in range(120):  # 120 * 5 s = 10 min per temp → ~60 min total
            p._telemetry.add_sample(appid, {"pl1": 15, "temp_cpu": t, "temp_gpu": t - 2}, dt=5.0)


# ---------------------------------------------------------------------------
# Learned-band state + dial RPC
# ---------------------------------------------------------------------------

def test_state_exposes_learned_no_game(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    # The battery↔performance dial is no longer backend state (it's local UI state on
    # the suggestion card); only the learned band is exposed.
    assert "tdp_dial" not in st
    assert st["learned"]["enough"] is False
    assert st["learned"]["reason"] == "no_game"


def test_learned_disabled_when_telemetry_off(Plugin):
    p = Plugin()
    p._init()
    p._settings["telemetry_enabled"] = False
    st = asyncio.run(p.get_tdp_state())
    assert st["learned"]["reason"] == "disabled"


def test_learned_band_surfaces_when_enough_data(Plugin):
    p = Plugin()
    p._init()
    _feed_tdp_band(p)
    asyncio.run(p.set_current_game("123"))
    st = asyncio.run(p.get_tdp_state())
    assert st["learned"]["enough"] is True
    assert st["learned"]["floor"] == 15
    assert st["learned"]["ceil"] == 21


def test_reset_telemetry_wipes_learned_data(Plugin):
    p = Plugin()
    p._init()
    _feed_tdp_band(p)
    assert asyncio.run(p.get_telemetry("123"))["by_pl1"]  # has data
    assert asyncio.run(p.reset_telemetry()) is True
    assert asyncio.run(p.get_telemetry("123")) == {"samples_n": 0, "by_pl1": {}, "recent": []}
    # learned band now degrades honestly (no fabricated data)
    st = asyncio.run(p.set_current_game("123"))
    assert st["learned"]["enough"] is False


# ---------------------------------------------------------------------------
# Auto-TDP is DECOUPLED from the learned band: entering a game does NOT seed PL1
# from the band (that coupling made the loop self-fulfilling). The loop explores
# to its own level over the full device range; the band is only a suggestion.
# ---------------------------------------------------------------------------

def test_entering_game_does_not_seed_pl1_from_band(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    _feed_tdp_band(p)  # band floor=15, ceil=21; device active max = 35
    before = p._tdp_profiles.effective("123")["pl1"]
    st = asyncio.run(p.set_current_game("123"))
    # PL1 is untouched by game entry — no band-derived jump (decoupled control).
    assert st["levels"]["pl1"] == before
    # …and the band is still exposed for the separate suggestion card.
    assert st["learned"]["enough"] is True
    assert st["learned"]["floor"] == 15 and st["learned"]["ceil"] == 21


# ---------------------------------------------------------------------------
# Auto loop: exploration cadence + recovery (the band-cage breaker glue)
# ---------------------------------------------------------------------------

def _run_loop_ticks(p, reads, _monkeypatch):
    samples = iter(reads)
    current = {"fps": None, "gpu_busy": None, "watts": None, "reason": "fps_unavailable"}
    sample_at = 0.0
    original_controller = sys.modules["main"].auto_tdp.AutoTdpController

    def timed_controller(*args, **kwargs):
        kwargs["clock"] = lambda: sample_at
        return original_controller(*args, **kwargs)

    _monkeypatch.setattr(
        sys.modules["main"].auto_tdp,
        "AutoTdpController",
        timed_controller,
    )

    def power_read():
        nonlocal current, sample_at
        current = next(samples)
        sample_at += 5.0
        return {"gpu_busy": current.get("gpu_busy"), "watts": current.get("watts")}

    def fps_read(expected_appid=None):
        fps = current.get("fps")
        reason = current.get("reason", "ok" if fps is not None else "fps_unavailable")
        return {
            "fps": fps,
            "focus": expected_appid,
            "age_s": 0.0 if fps is not None else None,
            "sample_at": sample_at if fps is not None else None,
            "available": reason == "ok",
            "reason": reason,
        }

    p._power_reader.read = power_read
    p._gamescope_stats.read = fps_read
    p._reset_auto_session("test")
    scope = "game" if p._current_appid is not None else "global"
    p._tdp_profiles.set_auto_tdp(scope, True, appid=p._current_appid)
    for _ in reads:
        asyncio.run(p._auto_tick())


def test_loop_warmup_holds_without_sawtooth(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"  # per-game control needs a running game
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"fps": 40, "gpu_busy": 92, "watts": 20} for _ in range(2)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 22
    assert p._tdp_profiles.effective("g")["pl1"] == 22


def test_loop_probes_down_only_one_watt_after_stable_fps(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    cap = p._effective_levels("g")[1]  # active max ceiling
    p._tdp_profiles.set_pl1("game", cap, appid="g")
    assert p._effective_levels("g")[0]["pl1"] == cap  # start pinned at the cap
    reads = [{"fps": 40, "gpu_busy": 80, "watts": 34} for _ in range(12)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == cap - 1
    assert p._tdp_profiles.effective("g")["pl1"] == cap


def test_loop_never_persists_its_dynamic_drop(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"fps": 40, "gpu_busy": 70, "watts": 20} for _ in range(12)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 21
    assert p._tdp_profiles.effective("g")["pl1"] == 22


def test_loop_steps_up_when_fps_is_below_target(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"fps": 35, "gpu_busy": 40, "watts": 18} for _ in range(4)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 28
    assert p._tdp_profiles.effective("g")["pl1"] == 20


def test_loop_clamps_recovery_to_automatic_device_max(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 35, appid="g")
    reads = [{"fps": 20, "gpu_busy": 99, "watts": 35}]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 35
    assert p._auto_status["reason"] == "at_maximum"


def test_loop_holds_with_no_signal(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"reason": "fps_unavailable"} for _ in range(8)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 20
    assert p._auto_status["state"] == "paused"
    assert p._tdp_profiles.effective("g")["pl1"] == 20


def test_loop_does_not_touch_global_when_no_game(Plugin, monkeypatch):
    # Auto-TDP is a per-GAME dynamic control. With no game running (desktop/loading)
    # the loop must NOT adjust the global PL1 — even if the desktop briefly saturates
    # the GPU. Otherwise a stray high-GPU tick would ramp the global setpoint.
    p = Plugin()
    p._init()
    p._current_appid = None
    p._tdp_profiles.set_pl1("global", 20)
    reads = [{"gpu_busy": 99, "watts": 30.0} for _ in range(4)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective(None)["pl1"] == 20  # global untouched


def test_loop_never_writes_when_backend_disables_auto_tdp(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._tdp_backend.auto_tdp_supported = False
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"gpu_busy": 99} for _ in range(4)]

    _run_loop_ticks(p, reads, monkeypatch)

    assert p._tdp_profiles.effective("g")["pl1"] == 20
    assert p._tdp_backend._levels is None


def test_loop_reports_recovery_state_after_pl1_change(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"fps": 35, "gpu_busy": 99, "watts": 20}]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_status["state"] == "recovering"
    assert p._auto_status["setpoint"] == 22


def test_signal_loss_during_protected_cooldown_reapplies_last_stable_tdp(
    Plugin, monkeypatch
):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [
        {"fps": 40, "gpu_busy": 80, "watts": 18} for _ in range(8)
    ] + [{"reason": "fps_stale", "gpu_busy": 0, "watts": 0}]

    _run_loop_ticks(p, reads, monkeypatch)

    assert p._auto_setpoint == 20
    assert p._tdp_backend._applied == 20
    assert p._auto_status["state"] == "paused"
    assert p._auto_status["reason"] == "fps_stale"


def test_unconfirmed_probe_is_rolled_back_and_never_learned(
    Plugin, monkeypatch
):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    original_set_levels = p._tdp_backend.set_levels
    calls = 0

    def set_levels(pl1, pl2, pl3, ac):
        nonlocal calls
        calls += 1
        if calls == 2:
            return TdpResult(pl1, None, True, "unconfirmed")
        return original_set_levels(pl1, pl2, pl3, ac)

    p._tdp_backend.set_levels = set_levels
    learned = []
    p._auto_learning.record = lambda *_args, **_kwargs: learned.append(True)
    reads = [{"fps": 40, "gpu_busy": 80, "watts": 18} for _ in range(6)]

    _run_loop_ticks(p, reads, monkeypatch)

    assert p._auto_setpoint == 20
    assert p._tdp_backend._applied == 20
    assert p._auto_status["state"] == "paused"
    assert p._auto_status["reason"] == "apply_unconfirmed"
    assert learned == []


def test_loop_does_not_learn_probe_before_protected_cooldown_finishes(
    Plugin, monkeypatch
):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    cap = p._effective_levels("g")[1]
    p._tdp_profiles.set_pl1("game", cap, appid="g")
    learned = []

    def record(_appid, _target_fps, _on_ac, setpoint, *, stable):
        learned.append((setpoint, stable))
        return True

    p._auto_learning.record = record
    reads = [{"fps": 40, "gpu_busy": 80, "watts": 18} for _ in range(10)]

    _run_loop_ticks(p, reads, monkeypatch)

    assert p._auto_setpoint == cap - 1
    assert p._auto_status["reason"] == "cooldown"
    assert learned == []


def test_failed_hardware_rollback_keeps_retry_aimed_at_safe_setpoint(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    now = {"value": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: now["value"])
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 6, appid="g")
    original_set_levels = p._tdp_backend.set_levels
    writes = []

    def set_levels(pl1, pl2, pl3, ac):
        writes.append(pl1)
        if len(writes) == 3:
            return TdpResult(pl1, None, False, "rollback-failed")
        return original_set_levels(pl1, pl2, pl3, ac)

    p._tdp_backend.set_levels = set_levels
    reads = [
        {"fps": 40, "gpu_busy": 80, "watts": 6} for _ in range(8)
    ] + [{"fps": 39, "gpu_busy": 80, "watts": 5}]

    _run_loop_ticks(p, reads, monkeypatch)

    assert writes == [6, 5, 6]
    assert p._auto_setpoint == 6
    assert p._auto_apply_blocked is True
    assert p._auto_status["reason"] == "apply_failed"

    p._power_reader.read = lambda: {"fps": 40, "gpu_busy": 80, "watts": 5}
    p._gamescope_stats.read = lambda expected_appid=None: {
        "fps": 40,
        "focus": expected_appid,
        "age_s": 0,
        "sample_at": 50,
        "available": True,
        "reason": "ok",
    }
    now["value"] += 2
    asyncio.run(p._auto_tick())

    assert writes == [6, 5, 6, 6]
    assert p._tdp_backend._applied == 6
    assert p._auto_apply_blocked is False


def test_loop_keeps_bounded_status_history_while_holding(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"fps": 40, "gpu_busy": 92, "watts": 20} for _ in range(48)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert len(p._auto_history) <= 32
    assert p._tdp_profiles.effective("g")["pl1"] == 22


def test_tick_abandons_a_decision_when_game_changes_during_power_read(
    Plugin, monkeypatch
):
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_tdp("global", True)
    started = threading.Event()
    release = threading.Event()

    def blocked_power_read():
        started.set()
        release.wait(timeout=2)
        return {"gpu_busy": 99, "watts": 20}

    p._power_reader.read = blocked_power_read
    p._gamescope_stats.read = lambda expected_appid=None: {
        "fps": 20,
        "focus": expected_appid,
        "age_s": 0,
        "sample_at": 1,
        "available": True,
        "reason": "ok",
    }
    p._tdp_backend.set_levels_calls = 0

    async def run_race():
        task = asyncio.create_task(p._auto_tick())
        await asyncio.to_thread(started.wait, 1)
        p._set_current_appid("99")
        release.set()
        await task

    asyncio.run(run_race())

    assert p._current_appid == "99"
    assert p._tdp_backend.set_levels_calls == 0
    assert p._auto_status["reason"] == "context_changed"


def test_tick_abandons_ac_setpoint_when_power_source_changes_during_read(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    on_ac = {"value": True}
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": on_ac["value"])
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 30)
    p._tdp_profiles.set_auto_tdp("global", True)
    started = threading.Event()
    release = threading.Event()
    writes = []

    def blocked_power_read():
        started.set()
        release.wait(timeout=2)
        return {"gpu_busy": 99, "watts": 30}

    original_set_levels = p._tdp_backend.set_levels

    def record_set_levels(pl1, pl2, pl3, ac):
        writes.append((pl1, ac))
        return original_set_levels(pl1, pl2, pl3, ac)

    p._power_reader.read = blocked_power_read
    p._tdp_backend.set_levels = record_set_levels
    p._gamescope_stats.read = lambda expected_appid=None: {
        "fps": 20,
        "focus": expected_appid,
        "age_s": 0,
        "sample_at": 1,
        "available": True,
        "reason": "ok",
    }

    async def run_race():
        task = asyncio.create_task(p._auto_tick())
        await asyncio.to_thread(started.wait, 1)
        on_ac["value"] = False
        release.set()
        await task

    asyncio.run(run_race())

    assert writes == []
    assert p._auto_context[3] is False
    assert p._auto_controller.max_w == 35


def test_queued_ac_command_is_rejected_if_unplugged_before_worker_runs(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    on_ac = {"value": True}
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": on_ac["value"])
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 30)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._ensure_auto_session(on_ac=True)
    command = p._capture_tdp_command("auto-step", on_ac=True)
    writes = []
    p._tdp_backend.set_levels = (
        lambda pl1, pl2, pl3, ac: writes.append((pl1, ac))
    )

    on_ac["value"] = False
    result = p._execute_tdp_command(command)

    assert result.ok is False
    assert result.detail == "stale-power-source"
    assert writes == []


def test_queued_ac_command_is_rejected_if_unplugged_during_worker_readback(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    on_ac = {"value": True}
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": on_ac["value"])
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    command = p._capture_tdp_command("auto-step", on_ac=True)
    original_observe = p._observe_tdp_sync
    writes = []

    def unplug_during_observe():
        observation = original_observe()
        on_ac["value"] = False
        return observation

    p._observe_tdp_sync = unplug_during_observe
    p._tdp_backend.set_levels = (
        lambda pl1, pl2, pl3, ac: writes.append((pl1, ac))
    )

    result = p._execute_tdp_command(command)

    assert result.ok is False
    assert result.detail == "stale-power-source"
    assert writes == []


def test_live_primary_limit_clamps_auto_session_and_accepts_constrained_seed(
    Plugin,
):
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 30)
    p._tdp_profiles.set_auto_tdp("global", True)
    applied = {"watts": 20}

    def observe():
        return TdpObservation(
            readable=True,
            surfaces={
                "fake": {
                    rail: RailReading(applied["watts"], 5, 25)
                    for rail in ("pl1", "pl2", "pl3")
                },
            },
        )

    def set_levels(pl1, pl2, pl3, ac):
        applied["watts"] = min(pl1, 25)
        p._tdp_backend._applied = applied["watts"]
        return TdpResult(pl1, applied["watts"], True, "")

    p._tdp_backend.observe = observe
    p._tdp_backend.set_levels = set_levels
    p._ensure_auto_session(on_ac=True)

    asyncio.run(p._apply_auto_seed("test", on_ac=True))

    assert p._auto_controller.max_w == 25
    assert p._auto_setpoint == 25
    assert p._auto_applied is True
    assert p._auto_apply_blocked is False


def test_unconfirmed_apply_recovers_with_confirmed_retry_after_backoff(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    now = {"value": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: now["value"])
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 16)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._gamescope_stats.read = lambda expected_appid=None: {
        "fps": 40.0,
        "focus": "42",
        "age_s": 0,
        "sample_at": 100,
        "available": True,
        "reason": "ok",
    }
    p._power_reader.read = lambda: {"watts": 16.0, "gpu_busy": 80.0}
    original_set_levels = p._tdp_backend.set_levels
    calls = []

    def flaky_set_levels(pl1, pl2, pl3, ac):
        calls.append(pl1)
        if len(calls) == 1:
            return TdpResult(pl1, None, True, "unconfirmed")
        return original_set_levels(pl1, pl2, pl3, ac)

    p._tdp_backend.set_levels = flaky_set_levels

    asyncio.run(p._auto_tick())
    assert p._auto_apply_blocked is True
    asyncio.run(p._auto_tick())
    assert calls == [16]

    now["value"] += 2.0
    asyncio.run(p._auto_tick())

    assert calls == [16, 16]
    assert p._auto_apply_blocked is False
    assert p._auto_applied is True
    assert p._auto_status["reason"] == "apply_recovered"


def test_unconfirmed_apply_stops_writing_after_three_spaced_retries(
    Plugin, monkeypatch
):
    main = sys.modules["main"]
    now = {"value": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: now["value"])
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 16)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._gamescope_stats.read = lambda expected_appid=None: {
        "fps": 40.0,
        "focus": "42",
        "age_s": 0,
        "sample_at": now["value"],
        "available": True,
        "reason": "ok",
    }
    p._power_reader.read = lambda: {"watts": 16.0, "gpu_busy": 80.0}
    writes = []

    def unconfirmed(pl1, pl2, pl3, ac):
        writes.append(pl1)
        return TdpResult(pl1, None, True, "unconfirmed")

    p._tdp_backend.set_levels = unconfirmed

    asyncio.run(p._auto_tick())
    for delay in (2.0, 8.0, 30.0):
        now["value"] += delay
        asyncio.run(p._auto_tick())
    assert writes == [16, 16, 16, 16]

    now["value"] += 30.0
    asyncio.run(p._auto_tick())
    now["value"] += 30.0
    asyncio.run(p._auto_tick())

    assert writes == [16, 16, 16, 16]
    assert p._auto_apply_exhausted is True


def test_set_ui_active_pauses_auto_without_changing_power(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 17, appid="g")
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 40, 17, appid="g")
    p._ensure_auto_session(on_ac=True)
    before = (p._tdp_backend._applied, p._tdp_backend._levels)

    assert asyncio.run(p.set_ui_active(True)) is True

    assert p._auto_setpoint == 17
    assert p._auto_status["state"] == "paused"
    assert p._auto_status["reason"] == "ui_active"
    assert (p._tdp_backend._applied, p._tdp_backend._levels) == before


def test_set_ui_active_raises_a_reduced_auto_session_to_its_initial_tdp(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 40, 15, appid="g")
    controller, _created = p._ensure_auto_session(on_ac=True)
    controller.setpoint = 5
    p._auto_setpoint = 5
    p._auto_applied = True
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)

    assert asyncio.run(p.set_ui_active(True)) is True

    assert p._tdp_backend._applied == 15
    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_status["reason"] == "ui_active"
    assert p._auto_status["held_watts"] == 15


@pytest.mark.parametrize("minimum, maximum, expected", [
    (None, None, 15),
    (None, 10, 10),
    (20, 25, 20),
])
def test_ui_floor_uses_device_default_within_requested_range(Plugin, minimum, maximum, expected):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 40, 5, appid="g", min_tdp=minimum, max_tdp=maximum)
    controller, _ = p._ensure_auto_session(True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    setpoint = controller.setpoint

    asyncio.run(p.set_ui_active(True))

    assert p._tdp_backend._levels == (expected, expected, expected)
    assert p._auto_status["held_watts"] == expected
    assert p._auto_setpoint == setpoint
    assert p._tdp_profiles.auto_config("g")["initial_tdp"] == 5
    assert p._tdp_history[-1]["reason"] == "auto-ui-floor"


def test_steam_focus_applies_ui_floor_without_changing_auto_setpoint(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 30, 5, appid="g")
    p._ensure_auto_session(on_ac=True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    p._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    p._gamescope_stats.start = lambda: None
    reading = {
        "fps": None,
        "focus": "steam",
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }
    p._gamescope_stats.read = lambda: reading

    status = asyncio.run(p._auto_tick())

    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_setpoint == 5
    assert status["reason"] == "no_game_focus"
    assert status["held_watts"] == 15
    assert p._tdp_history[-1]["reason"] == "auto-focus-floor"

    reading.update({
        "fps": 30.0,
        "focus": "g",
        "age_s": 0.0,
        "sample_at": 1.0,
        "available": True,
        "reason": "ok",
    })
    status = asyncio.run(p._auto_tick())

    assert p._tdp_backend._levels == (5, 5, 5)
    assert p._auto_setpoint == 5
    assert status["held_watts"] is None


def test_missing_focus_applies_responsive_floor_while_auto_is_active(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 30, 5, appid="g")
    p._ensure_auto_session(on_ac=True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    p._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    p._gamescope_stats.start = lambda: None
    p._gamescope_stats.read = lambda: {
        "fps": None,
        "focus": None,
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }

    status = asyncio.run(p._auto_tick())

    assert p._tdp_backend._levels == (15, 15, 15)
    assert status["reason"] == "no_game_focus"
    assert status["held_watts"] == 15


def test_failed_focus_floor_respects_auto_apply_backoff(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 30, 5, appid="g")
    p._ensure_auto_session(on_ac=True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    p._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    p._gamescope_stats.start = lambda: None
    p._gamescope_stats.read = lambda: {
        "fps": None,
        "focus": "steam",
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }
    writes = []

    def reject(pl1, pl2, pl3, ac):
        writes.append((pl1, pl2, pl3, ac))
        return TdpResult(pl1, None, False, "rejected")

    p._tdp_backend.set_levels = reject

    asyncio.run(p._auto_tick())
    asyncio.run(p._auto_tick())

    assert len(writes) == 1
    assert p._auto_status["held_watts"] is None


def test_focus_change_during_floor_restores_auto_setpoint_on_next_tick(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 30, 5, appid="g")
    p._ensure_auto_session(on_ac=True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    p._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    p._gamescope_stats.start = lambda: None
    reading = {
        "fps": None,
        "focus": "steam",
        "age_s": None,
        "sample_at": None,
        "available": False,
        "reason": "no_game_focus",
    }
    p._gamescope_stats.read = lambda: reading
    original_set_levels = p._tdp_backend.set_levels

    def apply_then_focus_game(pl1, pl2, pl3, ac):
        result = original_set_levels(pl1, pl2, pl3, ac)
        reading.update({
            "fps": 30.0,
            "focus": "g",
            "age_s": 0.0,
            "sample_at": 1.0,
            "available": True,
            "reason": "ok",
        })
        return result

    p._tdp_backend.set_levels = apply_then_focus_game

    asyncio.run(p._auto_tick())
    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_status["held_watts"] is None

    asyncio.run(p._auto_tick())

    assert p._tdp_backend._levels == (5, 5, 5)
    assert p._auto_setpoint == 5


@pytest.mark.parametrize("maximum, expected", [(None, 15), (10, 10)])
def test_game_exit_keeps_global_auto_grid_floor_and_restores_manual_on_disable(Plugin, maximum, expected):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_pl1("global", 5)
    p._tdp_profiles.set_offsets("global", 3, 4)
    p._tdp_profiles.set_auto_config("global", 40, 5, max_tdp=maximum)
    p._tdp_profiles.set_auto_tdp("global", True)
    asyncio.run(p.set_current_game("42"))

    asyncio.run(p.set_current_game(None))

    assert p._tdp_backend._levels == (expected, expected, expected)
    assert p._auto_controller is None
    assert p._auto_setpoint is None
    assert p._tdp_profiles.effective(None)["pl1"] == 5
    asyncio.run(p.set_auto_tdp(False))
    assert p._tdp_backend._levels == (5, 8, 12)


@pytest.mark.parametrize("gate", ["auto", "safe", "control", "eco", "module", "firmware", "owner"])
def test_grid_floor_requires_global_auto_and_all_control_gates(Plugin, monkeypatch, gate):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_pl1("global", 5)
    p._tdp_profiles.set_auto_tdp("global", True)
    if gate == "auto":
        p._tdp_profiles.set_auto_tdp("global", False)
    elif gate == "safe":
        p._tdp_backend.auto_tdp_safe = False
    elif gate == "control":
        p._settings["tdp_control_enabled"] = False
    elif gate == "eco":
        p._settings["eco_enabled"] = True
    elif gate == "module":
        monkeypatch.setattr(p, "_module_enabled", lambda _mid: False)
    elif gate == "firmware":
        monkeypatch.setattr(p, "_firmware_mode", lambda: "performance")
    else:
        monkeypatch.setattr(p, "_tdp_write_authorized", lambda: False)

    command = p._capture_tdp_command("reapply")

    assert command.logical_requested == {"pl1": 5, "pl2": 5, "pl3": 5}
    assert p._auto_controller is None


def test_ui_floor_discards_observation_when_game_changes_during_read(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._set_current_appid("old")
    p._tdp_profiles.set_auto_config("global", 40, 5)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._ensure_auto_session(True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)

    async def switch_game_during_read():
        observation = p._observe_tdp_sync()
        p._set_current_appid("new")
        p._ensure_auto_session(True)
        return observation

    monkeypatch.setattr(p, "_read_tdp_observation", switch_game_during_read)
    asyncio.run(p.set_ui_active(True))

    assert p._current_appid == "new"
    assert p._tdp_backend._levels == (5, 5, 5)
    assert p._auto_ui_hold_watts is None


def test_grid_auto_toggle_applies_while_menu_is_open(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_pl1("global", 5)
    asyncio.run(p.set_ui_active(True))

    asyncio.run(p.set_auto_tdp(True))
    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_controller is None


def test_game_auto_toggle_applies_ui_floor_when_menu_is_already_open(Plugin):
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_pl1("game", 5, appid="42")
    p._tdp_profiles.set_auto_config("game", 40, 5, appid="42")
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    asyncio.run(p.set_ui_active(True))

    asyncio.run(p.set_auto_tdp(True, "game", "42", "42"))

    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_status["state"] == "paused"
    assert p._auto_status["reason"] == "ui_active"
    assert p._auto_status["held_watts"] == 15


def test_grid_auto_range_edit_applies_while_menu_is_open(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_auto_tdp("global", True)
    p._tdp_backend._levels = (15, 15, 15)
    p._tdp_backend._applied = 15
    asyncio.run(p.set_ui_active(True))
    asyncio.run(p.set_auto_tdp_config(40, 5, "global", None, None, None, 10))
    assert p._tdp_backend._levels == (10, 10, 10)
    assert p._auto_controller is None


def test_grid_auto_disable_restores_manual_while_menu_is_open(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_pl1("global", 5)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._tdp_backend._levels = (15, 15, 15)
    p._tdp_backend._applied = 15
    asyncio.run(p.set_ui_active(True))
    asyncio.run(p.set_auto_tdp(False))
    assert p._tdp_backend._levels == (5, 5, 5)
    assert p._auto_controller is None


@pytest.mark.parametrize("minimum, maximum, expected, bounds", [
    (None, 10, 10, (5, 10)),
    (20, None, 20, (20, 35)),
])
def test_game_range_edit_rebounds_open_qam_hold_immediately(
    Plugin, minimum, maximum, expected, bounds,
):
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 5)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._ensure_auto_session(True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    asyncio.run(p.set_ui_active(True))
    assert p._auto_status["held_watts"] == 15

    asyncio.run(p.set_auto_tdp_config(40, 5, "global", None, "42", minimum, maximum))

    assert p._tdp_backend._levels == (expected, expected, expected)
    assert p._auto_status["held_watts"] == expected
    assert p._ui_active is True
    assert (p._auto_controller.min_w, p._auto_controller.max_w) == bounds
    assert p._auto_setpoint == bounds[0]
    assert p._tdp_profiles.auto_config(None)["initial_tdp"] == 5
    assert p._tdp_history[-1]["reason"] == "auto-ui-floor"


@pytest.mark.parametrize("boundary", ["observation", "apply"])
def test_game_range_edit_discards_stale_ui_floor_on_context_change(Plugin, monkeypatch, boundary):
    p = Plugin()
    p._init()
    p._set_current_appid("42")
    p._tdp_profiles.set_auto_config("global", 40, 5)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._ensure_auto_session(True)
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)
    asyncio.run(p.set_ui_active(True))
    reached_boundary = []

    def switch_context():
        reached_boundary.append(True)
        p._set_current_appid("new")
        p._ensure_auto_session(True)

    if boundary == "observation":
        original = p._read_tdp_observation

        async def change_during_read():
            observation = await original()
            if not reached_boundary:
                switch_context()
            return observation

        monkeypatch.setattr(p, "_read_tdp_observation", change_during_read)
    else:
        async def change_before_command():
            switch_context()

        monkeypatch.setattr(p, "_ensure_recognised_desktop_migration", change_before_command)

    asyncio.run(p.set_auto_tdp_config(40, 5, "global", None, "42", None, 10))

    assert reached_boundary
    assert p._current_appid == "new"
    assert p._tdp_backend._levels == (15, 15, 15)
    assert p._auto_setpoint == 5
    assert p._auto_ui_hold_watts is None


def test_leaving_ui_reapplies_the_auto_setpoint_on_the_next_fps_sample(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 40, 15, appid="g")
    controller, _created = p._ensure_auto_session(on_ac=True)
    controller.setpoint = 5
    p._auto_setpoint = 5
    p._auto_applied = True
    p._tdp_backend._applied = 5
    p._tdp_backend._levels = (5, 5, 5)

    asyncio.run(p.set_ui_active(True))
    assert p._tdp_backend._applied == 15
    asyncio.run(p.set_ui_active(False))
    p._power_reader.read = lambda: {"watts": 6.0, "gpu_busy": 50.0}
    stats = GamescopeStats(clock=lambda: 100.0)
    stats._apply_line("fps=40")
    stats._apply_line("focus=42")
    stats.start = lambda: None
    p._gamescope_stats = stats

    asyncio.run(p._auto_tick())

    assert p._tdp_backend._applied == 5
    assert p._tdp_backend._levels == (5, 5, 5)


def test_non_steam_profile_uses_fresh_fps_from_its_rendering_process(
    Plugin,
):
    p = Plugin()
    p._init()
    p._current_appid = "ns:pokémon blue"
    p._tdp_profiles.set_auto_config("global", 40, 15)
    p._tdp_profiles.set_auto_tdp("global", True)
    p._power_reader.read = lambda: {"watts": 11.0, "gpu_busy": 70.0}
    stats = GamescopeStats(clock=lambda: 100.0)
    stats._apply_line("fps=39.5")
    stats._apply_line("focus=-479910431")
    stats.start = lambda: None
    p._gamescope_stats = stats

    status = asyncio.run(p._auto_tick())

    assert status["reason"] == "awaiting_gameplay"
    assert status["fps"] == 39.5
    assert status["focus"] == "-479910431"


def test_game_context_change_discards_the_previous_renderers_fps(Plugin):
    p = Plugin()
    p._init()
    stats = GamescopeStats(clock=lambda: 100.0)
    stats._apply_line("fps=60")
    stats._apply_line("focus=42")
    p._gamescope_stats = stats

    p._set_current_appid("new-game")

    assert stats.read()["reason"] == "no_game_focus"


def test_ui_pause_keeps_reporting_physical_hold_across_config_changes(Plugin):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 17, appid="g")
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_auto_config("game", 40, 17, appid="g")
    p._ensure_auto_session(on_ac=True)
    p._tdp_backend._applied = 19
    p._tdp_backend._levels = (19, 19, 19)
    writes = []

    def record_write(pl1, pl2, pl3, ac):
        writes.append((pl1, pl2, pl3, ac))
        p._tdp_backend._applied = pl1
        p._tdp_backend._levels = (pl1, pl2, pl3)
        return TdpResult(pl1, pl1, True, "")

    p._tdp_backend.set_levels = record_write

    assert asyncio.run(p.set_ui_active(True)) is True
    assert p._auto_status["held_watts"] == 19

    asyncio.run(p.set_auto_tdp_config(40, 5, "game", "g", "g"))

    assert p._auto_status["state"] == "paused"
    assert p._auto_status["reason"] == "ui_active"
    assert p._auto_status["setpoint"] == 5
    assert p._auto_status["held_watts"] == 19
    assert p._tdp_backend._applied == 19
    assert writes == []

    assert asyncio.run(p.set_ui_active(False)) is False
    assert p._auto_status["held_watts"] is None


def test_loop_optimizes_low_demand_workload_after_qualification(
    Plugin,
    monkeypatch,
):
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 13, appid="g")
    reads = [{"fps": 60, "gpu_busy": 8, "watts": 6} for _ in range(13)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._auto_setpoint == 12


# ---------------------------------------------------------------------------
# Adaptive fan-curve MODE (choosing it IS the opt-in; drives the learned curve)
# ---------------------------------------------------------------------------

def test_adaptive_mode_drives_learned_curve_when_enough_data(Plugin):
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    asyncio.run(p.set_current_game("123"))
    st = asyncio.run(p.set_fan_adaptive("game", "123"))
    assert st["preset"] == "adaptive"
    assert p._fan_ctrl.applied is not None          # learned curve pushed to hardware
    assert len(p._fan_ctrl.applied) == 8


def test_adaptive_mode_no_data_falls_back_to_firmware_auto(Plugin):
    # adaptive with no learned data must NOT fabricate a curve — it
    # leaves the fans on firmware auto and shows the learning state.
    p = Plugin()
    p._init()
    asyncio.run(p.set_current_game("123"))
    st = asyncio.run(p.set_fan_adaptive("game", "123"))
    assert st["preset"] == "adaptive"
    assert p._fan_ctrl.applied is None              # nothing driven
    assert p._fan_ctrl.auto_called is True          # firmware auto instead


def test_preset_does_not_trigger_adaptive_learner(Plugin):
    # Choosing a fixed preset is an explicit choice → the learner never runs for it.
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    asyncio.run(p.set_current_game("123"))
    asyncio.run(p.set_fan_preset("silent", "game", "123"))
    p._fan_ctrl.applied = None
    p._maybe_reapply_adaptive_fan_curve()           # periodic re-fit tick
    assert p._fan_ctrl.applied is None              # untouched (not adaptive)


def test_custom_curve_not_touched_by_periodic_refit(Plugin):
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    p._current_appid = "123"
    manual = [[40, 0], [50, 30], [60, 60], [70, 90], [80, 150], [85, 200], [90, 255], [95, 255]]
    asyncio.run(p.set_fan_curve_points(manual, "game", "123"))
    before = list(p._fan_curves.effective("123")["points"])
    p._maybe_reapply_adaptive_fan_curve()
    assert p._fan_curves.effective("123")["points"] == before  # never touched
    assert p._fan_curves.effective("123")["preset"] == "custom"


def test_adaptive_bias_drives_biased_curve(Plugin):
    # The silence↔cool dial changes what the hardware runs (cooler = higher pwm).
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    asyncio.run(p.set_current_game("123"))
    asyncio.run(p.set_fan_adaptive("game", "123"))
    balanced = list(p._fan_ctrl.applied)
    asyncio.run(p.set_fan_adaptive_bias(100, "game", "123"))  # fully cool
    cool = list(p._fan_ctrl.applied)
    assert sum(pwm for _t, pwm in cool) >= sum(pwm for _t, pwm in balanced)
    assert asyncio.run(p.get_fan_curve_state())["bias"] == 100


def test_switching_to_preset_leaves_adaptive(Plugin):
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    asyncio.run(p.set_current_game("123"))
    asyncio.run(p.set_fan_adaptive("game", "123"))
    st = asyncio.run(p.set_fan_preset("performance", "game", "123"))
    assert st["preset"] == "performance"  # explicit choice wins; adaptive is gone


# ---------------------------------------------------------------------------
# Periodic re-fit of the adaptive curve (~30 min of play), following the
# recent thermal pattern. Anti-churn; only runs in adaptive mode.
# ---------------------------------------------------------------------------

def test_periodic_reapply_refreshes_when_band_shifts(Plugin):
    p = Plugin()
    p._init()
    _feed_temp_band(p)  # cool band 58-78
    asyncio.run(p.set_current_game("123"))
    asyncio.run(p.set_fan_adaptive("game", "123"))
    before = list(p._fan_ctrl.applied)
    # The game heats up: the decaying histogram now leans hot → the fit shifts.
    for tC in (82, 86, 88, 90, 92):
        for _ in range(240):  # ~20 min per bin of fresh hot dwell
            p._telemetry.add_sample("123", {"pl1": 15, "temp_cpu": tC, "temp_gpu": tC - 2}, dt=5.0)
    p._maybe_reapply_adaptive_fan_curve()
    assert list(p._fan_ctrl.applied) != before   # curve tracked the hotter zone


def test_periodic_reapply_noop_when_not_adaptive(Plugin):
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    p._current_appid = "123"  # default global/game = auto (not adaptive)
    p._fan_ctrl.applied = None
    p._maybe_reapply_adaptive_fan_curve()
    assert p._fan_ctrl.applied is None


def test_periodic_reapply_noop_when_curve_unchanged(Plugin):
    # Same band → curve_changed False → no re-drive (anti-churn).
    p = Plugin()
    p._init()
    _feed_temp_band(p)
    asyncio.run(p.set_current_game("123"))
    asyncio.run(p.set_fan_adaptive("game", "123"))
    p._fan_ctrl.applied = None  # sentinel: a re-drive would set it
    p._maybe_reapply_adaptive_fan_curve()  # nothing new learned
    assert p._fan_ctrl.applied is None


def _feed_temp_band_minutes(p, minutes, appid="123"):
    """Feed roughly *minutes* of spread temp dwell (below/above the 30-min gate)."""
    per_bin = max(1, int((minutes * 60) / (6 * 5)))
    for t in (58, 62, 66, 70, 74, 78):
        for _ in range(per_bin):
            p._telemetry.add_sample(appid, {"pl1": 15, "temp_cpu": t, "temp_gpu": t - 2}, dt=5.0)


def test_midsession_drive_fires_when_enough_crosses(Plugin):
    # In adaptive mode, once `enough_data` flips true MID-session the learned curve
    # must land on the very next in-game tick — not wait ~30 min for the re-fit.
    p = Plugin()
    p._init()
    p._current_appid = "123"
    p._fan_curves.set_adaptive("game", appid="123")
    p._adaptive_applied = False
    # Not enough yet (short dwell) → mid-session drive is a no-op.
    _feed_temp_band_minutes(p, 10)
    p._maybe_drive_adaptive_fan_curve()
    assert p._fan_ctrl.applied is None
    assert p._adaptive_applied is False
    # Now cross the gate; a single sample tick should trigger the gated drive.
    _feed_temp_band_minutes(p, 60)
    p._on_sample_collected(("123", {"temp_cpu": 70}))
    assert p._fan_ctrl.applied is not None
    assert p._adaptive_applied is True


def test_midsession_drive_noop_when_not_adaptive(Plugin):
    # The O(1) mode check runs first — no drive when the mode isn't adaptive,
    # even with plenty of data.
    p = Plugin()
    p._init()
    p._current_appid = "123"  # default = auto
    _feed_temp_band_minutes(p, 60)
    p._on_sample_collected(("123", {"temp_cpu": 70}))
    assert p._fan_ctrl.applied is None


def test_midsession_drive_runs_only_once_per_session(Plugin, monkeypatch):
    # Once driven, the per-tick suggestion is NOT recomputed every sample — only the
    # 30-min re-fit path runs thereafter.
    p = Plugin()
    p._init()
    p._current_appid = "123"
    p._fan_curves.set_adaptive("game", appid="123")
    _feed_temp_band_minutes(p, 60)
    p._on_sample_collected(("123", {"temp_cpu": 70}))  # drives, sets the flag
    assert p._adaptive_applied is True
    calls = {"n": 0}
    monkeypatch.setattr(p, "_maybe_drive_adaptive_fan_curve",
                        lambda: calls.__setitem__("n", calls["n"] + 1))
    p._on_sample_collected(("123", {"temp_cpu": 70}))
    assert calls["n"] == 0  # not called again — the flag short-circuits it


def test_reapply_ticks_reset_on_sampler_start(Plugin):
    p = Plugin()
    p._init()
    p._reapply_ticks = 200
    p._start_sampler()  # no event loop in tests → start() no-ops, but the reset happens
    assert p._reapply_ticks == 0


def test_sampler_tick_counter_triggers_reapply(Plugin, monkeypatch):
    # The re-fit is driven by in-game sampler ticks (~30 min of play), not wall clock.
    import main as main_mod
    p = Plugin()
    p._init()
    p._current_appid = "123"
    p._fan_curves.set_adaptive("game", appid="123")
    calls = {"n": 0}
    monkeypatch.setattr(p, "_maybe_reapply_adaptive_fan_curve",
                        lambda: calls.__setitem__("n", calls["n"] + 1))
    for _ in range(main_mod.Plugin._REAPPLY_EVERY_TICKS):
        res = p._collect_sample()
        p._on_sample_collected(res)
    assert calls["n"] == 1


def test_auto_scope_follows_global_until_game_has_own_profile(Plugin):
    # The auto machinery must NOT detach a game that follows global: while following,
    # it tunes the global profile the game inherits (scope "global"), never minting a
    # per-game profile behind the user's back. Only a game with its own profile is
    # tuned in "game" scope.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    assert p._tdp_profiles.is_following_global("g") is True
    assert p._auto_scope() == "global"
    p._tdp_profiles.set_pl1("game", 20, appid="g")   # game now has its own profile
    assert p._tdp_profiles.is_following_global("g") is False
    assert p._auto_scope() == "game"
    p._current_appid = None
    assert p._auto_scope() == "global"


def test_game_profiles_overview_lists_and_resets(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    p._cpu_profiles.set_smt("game", False, appid="g")
    rows = asyncio.run(p.list_game_profiles())
    row = next(r for r in rows if r["appid"] == "g")
    assert row["tdp"]["pl1"] == 22
    assert row["cpu"]["smt"] is False
    assert "fan" not in row  # no fan profile set for this game
    # Reset forgets the game across every store → it reverts to global.
    rows2 = asyncio.run(p.reset_game_profiles("g"))
    assert all(r["appid"] != "g" for r in rows2)
    assert p._tdp_profiles.has_game("g") is False
    assert p._cpu_profiles.has_game("g") is False


def test_game_profiles_overview_includes_the_full_auto_configuration(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_auto_config(
        "game",
        55,
        8,
        appid="g",
        min_tdp=5,
        max_tdp=14,
    )
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")

    rows = asyncio.run(p.list_game_profiles())
    row = next(r for r in rows if r["appid"] == "g")

    assert row["tdp"] == {
        "pl1": 10,
        "auto": True,
        "target_fps": 55,
        "initial_tdp": 8,
        "min_tdp": 5,
        "max_tdp": 14,
        "follows_global": False,
    }


def test_game_profiles_overview_keeps_own_auto_values_while_following_global(Plugin):
    p = Plugin()
    p._init()
    p._tdp_profiles.set_auto_config(
        "global",
        40,
        15,
        min_tdp=6,
        max_tdp=25,
    )
    p._tdp_profiles.set_auto_config(
        "game",
        55,
        8,
        appid="g",
        min_tdp=5,
        max_tdp=14,
    )
    p._tdp_profiles.set_auto_tdp("game", True, appid="g")
    p._tdp_profiles.set_follow_global("g", True)

    rows = asyncio.run(p.list_game_profiles())
    row = next(r for r in rows if r["appid"] == "g")

    assert row["tdp"] == {
        "pl1": 10,
        "auto": True,
        "target_fps": 55,
        "initial_tdp": 8,
        "min_tdp": 5,
        "max_tdp": 14,
        "follows_global": True,
    }


def test_overview_skips_tab_flip_with_no_real_change(Plugin):
    p = Plugin()
    p._init()
    # A bare scope-toggle (own profile seeded from global, nothing edited) must NOT show
    # up as a configured game.
    p._cpu_profiles.create_game_from_global("g")
    assert all(r["appid"] != "g" for r in asyncio.run(p.list_game_profiles()))
    # Once something actually differs from global, it appears.
    p._cpu_profiles.set_smt("game", False, appid="g")
    rows = asyncio.run(p.list_game_profiles())
    assert any(r["appid"] == "g" for r in rows)
