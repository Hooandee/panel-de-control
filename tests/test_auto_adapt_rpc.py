"""RPC-level regression coverage for the G auto-adaptation wiring (seed + dial +
fan auto-apply + learned-band state). Pure logic is unit-tested in
test_tdp_suggest / test_auto_tdp / test_fans_suggest; this locks the glue in main.py.
"""
import asyncio
import importlib
import sys
import types

import pytest

from tdp.types import TdpLimits, TdpResult


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

def _run_loop_ticks(p, reads, monkeypatch):
    """Drive _auto_loop for len(reads) ticks with a stubbed power reader + no real
    sleep, then stop. *reads* is a list of {"watts","gpu_busy"} dicts (one per tick)."""
    import main as main_mod

    import itertools

    # Pad the reader so it never StopIterations (which the loop would swallow and spin);
    # the counting decide is the deterministic stop after exactly len(reads) ticks.
    seq = itertools.chain(reads, itertools.repeat(reads[-1]))
    p._power_reader.read = lambda: next(seq)
    p._reset_auto_windows()

    state = {"n": 0, "sleeps": 0}
    real_decide = main_mod.auto_tdp.decide

    async def fake_sleep(_):
        # Safety stop independent of decide (the loop may `continue` before decide,
        # e.g. the no-game guard) so the test can't spin. Counts loop iterations and
        # caps a couple ticks past the read count; in the normal (game-running) path
        # counting_decide fires first, preserving its exact tick accounting.
        state["sleeps"] += 1
        if state["sleeps"] > len(reads) + 2:
            raise asyncio.CancelledError
        return None

    def counting_decide(*a, **k):
        state["n"] += 1
        if state["n"] > len(reads):
            raise asyncio.CancelledError
        return real_decide(*a, **k)

    monkeypatch.setattr(main_mod.auto_tdp, "decide", counting_decide)
    monkeypatch.setattr(main_mod.asyncio, "sleep", fake_sleep)
    asyncio.run(p._auto_loop())


def test_loop_holds_at_knee_no_sawtooth(Plugin, monkeypatch):
    # GPU ~92% (in the 88..97 dead-band = the knee) → the loop HOLDS, never the old
    # probe-down-every-tick sawtooth. (device active max = 35)
    p = Plugin()
    p._init()
    p._current_appid = "g"  # per-game control needs a running game
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"gpu_busy": 92} for _ in range(8)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective("g")["pl1"] == 22  # held — no sawtooth


def test_loop_power_limited_at_max_probes_down(Plugin, monkeypatch):
    # The power-limited case: pl1 at max (35), GPU stable 80% (below the 88 knee) → there
    # IS margin, so after the sustained-headroom gate it steps DOWN off the cap
    # (proportional to the gap), instead of holding at max forever like the old
    # watts model did (draw pinned the cap → "no headroom" → stuck).
    p = Plugin()
    p._init()
    p._current_appid = "g"
    cap = p._effective_levels("g")[1]  # active max ceiling
    p._tdp_profiles.set_pl1("game", cap, appid="g")
    assert p._effective_levels("g")[0]["pl1"] == cap  # start pinned at the cap
    reads = [{"gpu_busy": 80} for _ in range(8)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._effective_levels("g")[0]["pl1"] < cap  # dropped off the cap


def test_loop_drops_after_sustained_headroom(Plugin, monkeypatch):
    # GPU 40% (light) sustained past the gate → one proportional step down (gap
    # 88-40=48 → bounded to max_down_step 5): 22 → 17, then it re-observes.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"gpu_busy": 40} for _ in range(8)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective("g")["pl1"] == 17  # -max_down_step(5)


def test_loop_steps_up_when_saturated(Plugin, monkeypatch):
    # A saturating game (GPU 99%) ramps PL1 up to protect FPS.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"gpu_busy": 99} for _ in range(4)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective("g")["pl1"] == 28  # +2 W each of 4 ticks


def test_loop_holds_with_no_signal(Plugin, monkeypatch):
    # Level 4 (Claw today): no gpu_busy → hold, never thrash.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{} for _ in range(8)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective("g")["pl1"] == 20  # unchanged


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


def test_loop_clears_gpu_window_on_pl1_change(Plugin, monkeypatch):
    # A PL1 change must clear the GPU% window so it stays HOMOGENEOUS (only samples
    # taken at the CURRENT PL1). Otherwise decide averages GPU% across different PL1s.
    # During a continuous UP ramp (GPU 99 → +2/tick) every tick applies a change, so
    # after the last tick the window holds only THIS tick's single sample.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 20, appid="g")
    reads = [{"gpu_busy": 99} for _ in range(4)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert len(p._gpu_window) == 1


def test_loop_gpu_window_grows_while_holding(Plugin, monkeypatch):
    # When NOT changing PL1 (stable hold in the dead-band), the GPU% window must
    # ACCUMULATE homogeneous samples (real history for the headroom gate). No clear.
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 22, appid="g")
    reads = [{"gpu_busy": 92} for _ in range(5)]  # dead-band → hold
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._tdp_profiles.effective("g")["pl1"] == 22  # held
    # The harness appends one extra sample on the final (cancelling) tick before
    # decide raises, so 5 held ticks accumulate to 6 samples — the point is they
    # ACCUMULATE (were not cleared), unlike the change case.
    assert len(p._gpu_window) == 6


# ---------------------------------------------------------------------------
# QAM-open responsive floor (OPT-IN via qam_tdp_boost, default OFF): while the plugin
# UI is open AND the setting is on, the GPU-only loop uses a higher floor so the
# CPU-bound menu render stays fluid. set_ui_active bumps PL1 up to that floor
# immediately (only if below), and ui_floor_engaged is honest (True only when the
# floor is really holding PL1 above the loop's parked value). With the setting OFF
# (default) opening the QAM changes NOTHING — the loop shows the REAL in-game TDP.
# ---------------------------------------------------------------------------

def test_set_ui_active_bumps_pl1_up_when_below_floor(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 7, appid="g")  # sunk to device min
    assert asyncio.run(p.set_ui_active(True)) is True
    from auto_tdp import RESPONSIVE_FLOOR_W
    assert p._effective_levels("g")[0]["pl1"] == RESPONSIVE_FLOOR_W  # bumped up


def test_set_ui_active_does_not_lower_a_demanding_game(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 30, appid="g")  # already above the floor
    asyncio.run(p.set_ui_active(True))
    assert p._effective_levels("g")[0]["pl1"] == 30  # untouched


def test_set_ui_active_noop_when_auto_off(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = False
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 7, appid="g")
    asyncio.run(p.set_ui_active(True))
    assert p._effective_levels("g")[0]["pl1"] == 7  # manual mode untouched


def test_set_ui_active_noop_when_qam_boost_off(Plugin):
    # DEFAULT: the boost setting is off → opening the QAM must NOT raise PL1, so the
    # user sees the REAL in-game TDP (honesty over fluidity).
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    assert p._settings.get("qam_tdp_boost") is False  # default off
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 7, appid="g")  # sunk to device min
    asyncio.run(p.set_ui_active(True))
    assert p._effective_levels("g")[0]["pl1"] == 7  # unchanged, no silent boost


def test_ui_floor_engaged_true_only_when_raising(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 7, appid="g")
    asyncio.run(p.set_ui_active(True))  # bumps to the floor
    assert asyncio.run(p.get_power_draw())["ui_floor_engaged"] is True
    # A demanding game parked above the floor → the number IS the in-game one.
    p._tdp_profiles.set_pl1("game", 30, appid="g")
    assert asyncio.run(p.get_power_draw())["ui_floor_engaged"] is False


def test_ui_floor_engaged_false_when_qam_boost_off(Plugin):
    # DEFAULT: with the setting off there is no raise → engaged is always False even
    # with the UI open and PL1 at the device min (never claim a raise that isn't real).
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._current_appid = "g"
    p._ui_active = True
    p._tdp_profiles.set_pl1("game", 7, appid="g")
    assert asyncio.run(p.get_power_draw())["ui_floor_engaged"] is False


def test_ui_floor_engaged_false_when_ui_closed(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._tdp_profiles.set_pl1("game", 7, appid="g")
    assert asyncio.run(p.get_power_draw())["ui_floor_engaged"] is False


def test_ui_floor_engaged_false_when_no_game(Plugin):
    p = Plugin()
    p._init()
    p._settings["auto_tdp"] = True
    p._settings["qam_tdp_boost"] = True
    p._current_appid = None
    p._ui_active = True
    assert asyncio.run(p.get_power_draw())["ui_floor_engaged"] is False


def test_loop_respects_responsive_floor_while_ui_open(Plugin, monkeypatch):
    # With the setting ON and the UI open the loop must NOT sink below the responsive
    # floor even on a sustained GPU-light game (would starve the CPU-bound render).
    from auto_tdp import RESPONSIVE_FLOOR_W
    p = Plugin()
    p._init()
    p._settings["qam_tdp_boost"] = True
    p._current_appid = "g"
    p._ui_active = True
    p._tdp_profiles.set_pl1("game", RESPONSIVE_FLOOR_W, appid="g")
    reads = [{"gpu_busy": 40} for _ in range(12)]  # sustained headroom
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._effective_levels("g")[0]["pl1"] == RESPONSIVE_FLOOR_W  # floored


def test_loop_sinks_below_floor_when_qam_boost_off(Plugin, monkeypatch):
    # DEFAULT: setting off + UI open → the loop is free to drop below the responsive
    # floor to the device min (shows the real in-game TDP, no menu-time inflation).
    from auto_tdp import RESPONSIVE_FLOOR_W
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._ui_active = True  # UI open but boost setting off (default)
    p._tdp_profiles.set_pl1("game", RESPONSIVE_FLOOR_W, appid="g")
    reads = [{"gpu_busy": 40} for _ in range(12)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._effective_levels("g")[0]["pl1"] < RESPONSIVE_FLOOR_W  # dropped lower


def test_loop_sinks_below_floor_when_ui_closed(Plugin, monkeypatch):
    # Same game, UI closed → the loop is free to drop to device min for battery.
    from auto_tdp import RESPONSIVE_FLOOR_W
    p = Plugin()
    p._init()
    p._current_appid = "g"
    p._ui_active = False
    p._tdp_profiles.set_pl1("game", RESPONSIVE_FLOOR_W, appid="g")
    reads = [{"gpu_busy": 40} for _ in range(12)]
    _run_loop_ticks(p, reads, monkeypatch)
    assert p._effective_levels("g")[0]["pl1"] < RESPONSIVE_FLOOR_W  # dropped lower


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
