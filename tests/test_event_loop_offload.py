"""Guardrail: subprocess-backed applies (color / fans / TDP-ryzenadj) must run OFF
the event loop, so a wedged gamescope/systemctl/ryzenadj can't stall the auto-TDP
loop or any QAM RPC. See the off-load chokepoint helpers in main.Plugin.

The chokepoints run INLINE when no executor is installed (the state in every other
test → existing behaviour preserved). These tests install an executor to prove the
production dispatch actually goes off-loop.
"""
import asyncio
import concurrent.futures
import importlib
import sys
import threading
import types


class _RecordingExecutor(concurrent.futures.Executor):
    """Real Executor that records submissions and runs them inline (deterministic)."""

    def __init__(self):
        self.count = 0

    def submit(self, fn, *a, **k):
        self.count += 1
        f = concurrent.futures.Future()
        try:
            f.set_result(fn(*a, **k))
        except Exception as e:  # noqa: BLE001
            f.set_exception(e)
        return f


class _FakeColorBackend:
    def __init__(self):
        self.supported = True
        self.force_composite = False
        self.applied = []
        self.applied_threads = []

    def apply(self, state):
        self.applied.append(dict(state))
        self.applied_threads.append(threading.get_ident())
        return True


def _make_plugin(tmp_path, monkeypatch):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = True
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=20)

        def level_limits(self):
            return {}

        def set_tdp(self, w, ac):
            return TdpResult(w, w, True, "")

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    color = _FakeColorBackend()
    monkeypatch.setattr(main, "GamescopeColorBackend", lambda *a, **k: color)
    p = main.Plugin()
    p._init()
    return p, color


# ---- chokepoint helpers -------------------------------------------------------

def test_offload_call_runs_inline_and_returns_result_without_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p._offload_call(lambda: 42)) == 42


def test_offload_runs_inline_without_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    seen = []
    p._offload(lambda: seen.append(1))  # no executor, no loop → inline
    assert seen == [1]


def test_offload_call_dispatches_through_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec

    async def _run():
        return await p._offload_call(lambda: 7)

    assert asyncio.run(_run()) == 7
    assert rec.count == 1  # went THROUGH the executor, not the inline branch


def test_offload_runs_off_the_loop_thread(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex
    main_tid = threading.get_ident()

    async def _run():
        return await p._offload_call(threading.get_ident)

    ran_on = asyncio.run(_run())
    ex.shutdown()
    assert ran_on != main_tid  # executed off the event-loop thread


# ---- reapply paths dispatch off-loop -----------------------------------------

def test_reapply_all_offloads_tdp_fans_and_color(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec

    async def _run():
        p._reapply_all()  # sync, but under a running loop

    asyncio.run(_run())
    # tdp + fans + color offloaded; charge/cpu/gpu-clock stay inline (sysfs).
    assert rec.count == 3


def test_set_saturation_applies_color_off_loop(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex
    main_tid = threading.get_ident()
    st = asyncio.run(p.set_saturation(150, "global", None))
    ex.shutdown()
    assert st["saturation"] == 150
    assert color.applied[-1]["saturation"] == 150       # still reached the hardware
    assert color.applied_threads[-1] != main_tid        # off the loop thread


def test_set_tdp_watts_keeps_result_contract_when_offloaded(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec
    res = asyncio.run(p.set_tdp_watts(18, "global"))
    assert res["ok"] is True and res["applied_w"] is not None
    assert rec.count >= 1  # the TDP write went through the executor


class _SlowBackend:
    """TDP backend whose set_levels lags — so a readback that races an offloaded
    apply is deterministic (reads the stale value if not awaited)."""

    supported = True
    supports_levels = True
    name = "slow"

    def __init__(self):
        self._applied = 0

    def get_limits(self):
        from tdp.types import TdpLimits
        return TdpLimits(min_w=5, default_w=15, max_w=40, max_ac_w=40)

    def level_limits(self):
        return {}

    def set_levels(self, pl1, pl2, pl3, ac):
        import time
        from tdp.types import TdpResult
        time.sleep(0.05)
        self._applied = pl1
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied


class _FakeFan:
    """Fan backend that records the thread each hardware write runs on. On the Steam
    Deck this write is a blocking systemctl, so it MUST run off the loop thread."""

    def __init__(self):
        self.supported = True
        self.mode_based = False
        self.write_threads = []

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255,
                "mode_based": False, "mode": None}

    def apply_curve_all(self, points):
        self.write_threads.append(threading.get_ident())

    def set_auto(self, _mode):
        self.write_threads.append(threading.get_ident())

    def apply_preset(self, preset):
        self.write_threads.append(threading.get_ident())

    def restore_auto(self):
        self.write_threads.append(threading.get_ident())


def test_apply_rpcs_keep_subprocess_backends_off_the_loop_thread(tmp_path, monkeypatch):
    """Tripwire: every user apply path (color + fan RPCs, game change) must run the
    subprocess-spawning backends OFF the event-loop thread. Catches a future change
    that adds a blocking apply on the loop or drops the off-load — for any device."""
    p, color = _make_plugin(tmp_path, monkeypatch)
    fan = _FakeFan()
    p._fan_ctrl = fan
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def drive():
        loop_tid = threading.get_ident()
        await p.set_saturation(150, "global", None)
        await p.set_calibration(-20, 15)
        await p.preview_calibration(-10, 10)
        await p.reset_color()
        await p.set_fan_preset("balanced", "global", None)
        await p.set_fan_curve_points([[40, 30], [60, 50], [80, 90]], "global", None)
        await p.set_fan_auto("global", None)
        await p.create_game_profile("7")
        await p.set_current_game("7")
        await p._drain_offloaded()  # let fire-and-forget applies land
        return loop_tid

    loop_tid = asyncio.run(drive())
    ex.shutdown()
    assert color.applied_threads, "color apply never ran"
    assert fan.write_threads, "fan apply never ran"
    assert loop_tid not in color.applied_threads   # gamescopectl off the loop
    assert loop_tid not in fan.write_threads        # (Deck) systemctl off the loop


def test_set_current_game_state_reflects_the_offloaded_apply(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._tdp_backend = _SlowBackend()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex
    asyncio.run(p.create_game_profile("42"))
    asyncio.run(p.set_tdp_watts(25, "game", "42"))  # awaited → really applied
    p._tdp_backend._applied = 999                   # stale hardware readback
    st = asyncio.run(p.set_current_game("42"))       # re-applies (slow, off-loop)
    ex.shutdown()
    # The returned state must reflect the completed apply, not the stale 999.
    assert st["applied_w"] == 25
