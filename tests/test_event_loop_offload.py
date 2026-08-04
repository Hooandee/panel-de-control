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
import time
import types

import pytest


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


class _NeverCompletingExecutor(concurrent.futures.Executor):
    def __init__(self):
        self.submissions = 0
        self.shutdown_calls = []

    def submit(self, fn, *args, **kwargs):
        self.submissions += 1
        return concurrent.futures.Future()

    def shutdown(self, wait=True, *, cancel_futures=False):
        self.shutdown_calls.append((wait, cancel_futures))


class _BlockingCpuFrequency:
    supported = True
    backend = "blocking-cpufreq"

    def __init__(self, plugin):
        self.plugin = plugin
        self.started = threading.Event()
        self.release = threading.Event()
        self.window = (600_000, 3_000_000)
        self.requested = None
        self.auto_preserve_calls = []

    def set_window(self, minimum, maximum):
        from cpu.frequency import CpuFrequencyResult

        self.plugin._settings["cpu_frequency_handoff"] = {"baseline": "stock"}
        self.started.set()
        assert self.release.wait(timeout=2)
        self.window = (minimum, maximum)
        self.requested = (minimum, maximum)
        return CpuFrequencyResult(
            True, "applied", self.requested, self.window,
            {"attempted": False, "ok": None}, None, 0,
        )

    def set_auto(self, preserve_ownership=False):
        from cpu.frequency import CpuFrequencyResult

        self.auto_preserve_calls.append(bool(preserve_ownership))
        self.window = (600_000, 3_000_000)
        if not preserve_ownership:
            self.requested = None
            self.plugin._settings["cpu_frequency_handoff"] = None
        return CpuFrequencyResult(
            True, "restored", None, self.window,
            {"attempted": True, "ok": True}, None, 0,
        )

    def diagnostics(self):
        return {
            "requested": list(self.requested) if self.requested else None,
            "owned": self.plugin._settings.get("cpu_frequency_handoff") is not None,
            "policies": ["policy0"],
            "policy_state": [],
        }


class _FakeColorBackend:
    def __init__(self):
        self.supported = True
        self.probe_detail = "fake"
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


def test_offload_without_serial_executor_does_not_block_a_running_loop(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    release = threading.Event()
    results = []

    async def _run():
        asyncio.get_running_loop().call_later(0.02, release.set)
        p._offload(lambda: results.append(release.wait(0.3)))
        await asyncio.sleep(0.05)

    asyncio.run(_run())

    assert results == [True]


def test_offload_call_dispatches_through_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec

    async def _run():
        return await p._offload_call(lambda: 7)

    assert asyncio.run(_run()) == 7
    assert rec.count == 1  # went THROUGH the executor, not the inline branch


def test_gpd_fan_recovery_dispatches_through_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    calls = []
    p._device = types.SimpleNamespace(key="gpd_win_mini_2025")
    p._fan_ctrl = types.SimpleNamespace(supported=False)
    p._apply_executor = rec
    p._recover_gpd_fan_sync = lambda: calls.append("recover")

    asyncio.run(p._recover_gpd_fan())

    assert calls == ["recover"]
    assert rec.count == 1


def test_non_gpd_device_never_dispatches_fan_recovery(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    calls = []
    p._device = types.SimpleNamespace(key="generic")
    p._fan_ctrl = types.SimpleNamespace(supported=False)
    p._apply_executor = rec
    p._recover_gpd_fan_sync = lambda: calls.append("recover")

    asyncio.run(p._recover_gpd_fan())

    assert calls == []
    assert rec.count == 0


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

def test_reapply_all_keeps_hud_out_of_the_shared_apply_executor(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec

    async def _run():
        p._reapply_all()  # sync, but under a running loop

    asyncio.run(_run())
    # TDP + power handoff + fans + color use the shared worker. HUD has its own.
    assert rec.count == 4


def test_shared_apply_worker_progresses_while_hud_worker_is_blocked(
    tmp_path,
    monkeypatch,
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    started = threading.Event()
    release = threading.Event()
    p._hud_coordinator.call(
        p._hud_generation,
        lambda: (started.set(), release.wait(timeout=2)),
    )
    assert started.wait(timeout=1)
    p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    try:
        result = asyncio.run(p._offload_call(lambda: "tdp-progress"))
    finally:
        release.set()
        p._hud_generation += 1
        p._hud_coordinator.close(p._hud_generation, lambda: None)
        p._shutdown_apply_executor()

    assert result == "tdp-progress"


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


def test_unload_invalidates_a_queued_tdp_write_before_handoff(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    events = []
    blocker_started = threading.Event()
    release_blocker = threading.Event()

    def block_executor():
        blocker_started.set()
        release_blocker.wait(timeout=2)

    def write_levels(pl1, pl2, pl3, ac):
        from tdp.types import TdpResult
        events.append("write")
        return TdpResult(pl1, pl1, True, "")

    p._tdp_backend.set_levels = write_levels
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_hud_safe = lambda: None
    p._restore_hhd_tdp = lambda: events.append("handoff")

    async def run():
        p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        p._offload(block_executor)
        while not blocker_started.is_set():
            await asyncio.sleep(0)
        p._schedule_tdp_apply("queued-before-unload")
        release = threading.Timer(0.05, release_blocker.set)
        release.start()
        await p._unload()
        release.join()

    asyncio.run(run())
    assert events == ["handoff"]


def test_unload_stops_new_tdp_writes_before_handoff(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    events = []

    def write_levels(pl1, pl2, pl3, ac):
        from tdp.types import TdpResult
        events.append("write")
        return TdpResult(pl1, pl1, True, "")

    def handoff():
        events.append("handoff")
        p._schedule_tdp_apply("late-lifecycle")

    p._tdp_backend.set_levels = write_levels
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_hhd_tdp = handoff

    asyncio.run(p._unload())
    assert events == ["handoff"]


def test_unload_completes_without_yielding_to_the_stopping_event_loop(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._apply_executor = _RecordingExecutor()
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_power_handoff = lambda: True
    p._release_cpu_controls_sync = lambda _trigger: True
    p._release_gpu_clock_sync = lambda _trigger: True

    unload = p._unload()
    with pytest.raises(StopIteration):
        unload.send(None)


def test_unload_deadline_handoffs_now_and_again_behind_a_blocked_worker(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "_SHUTDOWN_DRAIN_TIMEOUT_S", 0.03)
    started = threading.Event()
    release = threading.Event()
    events = []

    def blocked_write():
        started.set()
        release.wait(timeout=1)
        events.append("late-write")

    p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    executor = p._apply_executor
    executor.submit(blocked_write)
    assert started.wait(timeout=1)
    p._restore_fans_safe = lambda: events.append("fans-handoff")
    p._restore_color_safe = lambda: events.append("color-handoff")
    p._restore_audio_safe = lambda: events.append("audio-handoff")
    p._release_cpu_controls_sync = lambda _trigger, **_kwargs: events.append("cpu-handoff") or True
    p._release_gpu_clock_sync = lambda _trigger, **_kwargs: events.append("gpu-handoff") or True
    p._restore_power_handoff = lambda **_kwargs: events.append("power-handoff") or True

    before = time.monotonic()
    asyncio.run(p._unload())
    elapsed = time.monotonic() - before

    assert elapsed < 0.15
    assert events == [
        "fans-handoff",
        "color-handoff",
        "audio-handoff",
        "cpu-handoff",
        "gpu-handoff",
        "power-handoff",
    ]
    release.set()
    executor.shutdown(wait=True)
    assert events == [
        "fans-handoff",
        "color-handoff",
        "audio-handoff",
        "cpu-handoff",
        "gpu-handoff",
        "power-handoff",
        "late-write",
        "fans-handoff",
        "color-handoff",
        "audio-handoff",
        "cpu-handoff",
        "gpu-handoff",
        "power-handoff",
    ]
    p._offload(lambda: events.append("post-unload-write"))
    assert "post-unload-write" not in events


def test_unload_attempts_emergency_handoff_when_worker_never_completes(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "_SHUTDOWN_DRAIN_TIMEOUT_S", 0.001)
    executor = _NeverCompletingExecutor()
    p._apply_executor = executor
    events = []
    p._restore_fans_safe = lambda: events.append("fans")
    p._restore_color_safe = lambda: events.append("color")
    p._restore_audio_safe = lambda: events.append("audio")
    p._release_cpu_controls_sync = lambda _trigger, **_kwargs: events.append("cpu") or True
    p._release_gpu_clock_sync = lambda _trigger, **_kwargs: events.append("gpu") or True
    p._restore_power_handoff = lambda **_kwargs: events.append("power") or True

    asyncio.run(p._unload())

    assert events == ["fans", "color", "audio", "cpu", "gpu", "power"]
    assert executor.submissions == 2
    assert executor.shutdown_calls == [(False, False)]


def test_unload_final_cpu_handoff_restores_after_late_manual_write(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    executor = p._apply_executor
    frequency = _BlockingCpuFrequency(p)
    p._cpu_frequency = frequency
    p._cpu_coordinator = None
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._release_gpu_clock_sync = lambda _trigger, **_kwargs: True
    p._restore_power_handoff = lambda **_kwargs: True
    p._drain_offloaded_sync = lambda _timeout: False
    generation = p._next_cpu_generation()
    intent = p._cpu_intent()
    intent["frequency"] = {
        "manual": True,
        "min_khz": 1_200_000,
        "max_khz": 2_400_000,
    }
    p._submit_offloaded(
        executor, lambda: p._run_cpu_apply(intent, generation)
    )
    assert frequency.started.wait(timeout=1)

    asyncio.run(p._unload())

    assert frequency.window == (600_000, 3_000_000)
    assert p._settings["cpu_frequency_handoff"] is not None, frequency.auto_preserve_calls
    frequency.release.set()
    executor.shutdown(wait=True)

    assert frequency.window == (600_000, 3_000_000)
    assert p._settings["cpu_frequency_handoff"] is None
    assert frequency.auto_preserve_calls == [True, False]


def test_unload_suppresses_done_callbacks_from_the_last_active_worker(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    started = threading.Event()
    release = threading.Event()
    events = []
    p._restore_fans_safe = lambda: events.append("handoff")
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._release_cpu_controls_sync = lambda _trigger: True
    p._release_gpu_clock_sync = lambda _trigger: True
    p._restore_power_handoff = lambda: True

    def active_write():
        started.set()
        release.wait(timeout=1)
        events.append("write")

    async def run():
        p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        p._offload(active_write, done=lambda: events.append("done-callback"))
        while not started.is_set():
            await asyncio.sleep(0)
        release.set()
        await p._unload()
        await asyncio.sleep(0)

    asyncio.run(run())

    assert events == ["write", "handoff"]


def test_unload_cancels_queued_mutation_and_handoffs_before_return(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    events = []
    started = threading.Event()
    release = threading.Event()
    p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    executor = p._apply_executor

    def bounded_active_job():
        started.set()
        release.wait(timeout=0.04)

    p._restore_fans_safe = lambda: events.append("fans-handoff")
    p._restore_color_safe = lambda: events.append("color-handoff")
    p._restore_audio_safe = lambda: events.append("audio-handoff")
    p._release_cpu_controls_sync = lambda _trigger: events.append("cpu-handoff") or True
    p._release_gpu_clock_sync = lambda _trigger: events.append("gpu-handoff") or True
    p._restore_power_handoff = lambda: events.append("power-handoff") or True

    async def drive():
        p._offload(bounded_active_job)
        while not started.is_set():
            await asyncio.sleep(0)
        p._offload(lambda: events.append("stale-write"))
        threading.Timer(0.01, release.set).start()
        await p._unload()

    asyncio.run(drive())
    executor.shutdown(wait=True)

    assert events == [
        "fans-handoff",
        "color-handoff",
        "audio-handoff",
        "cpu-handoff",
        "gpu-handoff",
        "power-handoff",
    ]


def test_unload_handoff_logs_report_actual_results(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    main = importlib.import_module("main")
    messages = []
    monkeypatch.setattr(
        main.decky.logger,
        "info",
        lambda message, *args: messages.append((message, args)),
    )
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._release_cpu_controls_sync = lambda _trigger: False
    p._release_gpu_clock_sync = lambda _trigger: True
    p._restore_power_handoff = lambda: False

    asyncio.run(p._unload())

    assert ("Shutdown stage unload:cpu-handoff ok=%s", (False,)) in messages
    assert ("Shutdown stage unload:gpu-handoff ok=%s", (True,)) in messages
    assert ("Shutdown stage unload:power-handoff ok=%s", (False,)) in messages


def test_uninstall_stops_new_tdp_writes_before_handoff(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    events = []

    def write_levels(pl1, pl2, pl3, ac):
        from tdp.types import TdpResult
        events.append("write")
        return TdpResult(pl1, pl1, True, "")

    def handoff():
        events.append("handoff")
        p._schedule_tdp_apply("late-lifecycle")

    p._tdp_backend.set_levels = write_levels
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_hud_safe = lambda: None
    p._restore_hhd_tdp = handoff
    monkeypatch.setattr(
        importlib.import_module("main").fan_expose,
        "remove_conf",
        lambda: None,
    )

    asyncio.run(p._uninstall())
    assert events == ["handoff"]


def test_uninstall_completes_without_yielding_to_the_stopping_event_loop(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._apply_executor = _RecordingExecutor()
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_power_handoff = lambda: True
    p._release_cpu_controls_sync = lambda _trigger: True
    p._release_gpu_clock_sync = lambda _trigger: True
    monkeypatch.setattr(
        importlib.import_module("main").fan_expose,
        "remove_conf",
        lambda: None,
    )

    uninstall = p._uninstall()
    with pytest.raises(StopIteration):
        uninstall.send(None)


class _SlowBackend:
    """TDP backend whose set_levels lags — so a readback that races an offloaded
    apply is deterministic (reads the stale value if not awaited)."""

    supported = True
    supports_levels = True
    blocking = True  # simulates the ryzenadj subprocess fallback (must run off-loop)
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
        self.write_threads = []

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255}

    def apply_curve_all(self, points):
        self.write_threads.append(threading.get_ident())

    def set_auto(self, _mode):
        self.write_threads.append(threading.get_ident())

    def restore_auto(self):
        self.write_threads.append(threading.get_ident())


class _RecordingReadFan(_FakeFan):
    def __init__(self):
        super().__init__()
        self.supported = False
        self.read_threads = []

    def read_state(self):
        self.read_threads.append(threading.get_ident())
        return {"supported": False, "source": "fake", "pwm_max": 255, "fans": []}


class _EmptyFanReader:
    def read(self):
        return {"supported": False, "fans": [], "temps": []}


class _RecordingCurveReader:
    def __init__(self):
        self.read_threads = []

    def read_curve(self):
        self.read_threads.append(threading.get_ident())
        return None


def test_fan_state_rpcs_read_hardware_off_the_loop_thread(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    fan = _RecordingReadFan()
    curve = _RecordingCurveReader()
    p._fan_ctrl = fan
    p._fan_reader = _EmptyFanReader()
    p._ec_curve = curve
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def read_states():
        loop_tid = threading.get_ident()
        await p.get_fan_state()
        await p.get_fan_curve_state()
        await p.set_fan_preset("balanced", "global", None)
        return loop_tid

    loop_tid = asyncio.run(read_states())
    ex.shutdown()
    assert fan.read_threads
    assert curve.read_threads
    assert loop_tid not in fan.read_threads
    assert loop_tid not in curve.read_threads


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
        await p.set_calibration({"temperature": -20, "contrast": 15})
        await p.preview_calibration({"temperature": -10, "contrast": 10})
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


def test_get_tdp_state_reads_applied_off_the_loop_thread(tmp_path, monkeypatch):
    """read_applied() spawns a subprocess on the ryzenadj fallback -> it must run
    off the event-loop thread, not inline in the async get_tdp_state handler."""
    p, _ = _make_plugin(tmp_path, monkeypatch)

    read_threads = []

    class _RecordingReadBackend(_SlowBackend):
        def read_applied(self):
            read_threads.append(threading.get_ident())
            return self._applied

    p._tdp_backend = _RecordingReadBackend()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex
    main_tid = threading.get_ident()
    st = asyncio.run(p.get_tdp_state())
    ex.shutdown()
    assert st["applied_w"] is not None
    assert read_threads and main_tid not in read_threads  # read_applied off the loop


def test_set_tdp_boost_mode_reads_applied_off_the_loop_thread(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)

    read_threads = []

    class _RecordingReadBackend(_SlowBackend):
        def read_applied(self):
            read_threads.append(threading.get_ident())
            return self._applied

    p._tdp_backend = _RecordingReadBackend()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex
    main_tid = threading.get_ident()
    asyncio.run(p.set_tdp_boost_mode("auto", "global"))
    ex.shutdown()
    assert read_threads and main_tid not in read_threads


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


def test_tdp_guard_observes_and_writes_off_the_loop_thread(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    observe_threads = []
    write_threads = []

    class _RecordingBackend(_SlowBackend):
        supports_levels = False

        def observe(self):
            from tdp.types import RailReading, TdpObservation

            observe_threads.append(threading.get_ident())
            return TdpObservation(
                readable=True,
                surfaces={
                    self.name: {
                        "pl1": RailReading(self._applied, 5, 40),
                    },
                },
            )

        def set_levels(self, pl1, pl2, pl3, ac):
            from tdp.types import TdpResult

            write_threads.append(threading.get_ident())
            self._applied = pl1
            return TdpResult(pl1, pl1, True, "")

    backend = _RecordingBackend()
    backend._applied = 30
    p._tdp_backend = backend
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def drive():
        loop_tid = threading.get_ident()
        await p._offload_call(lambda: p._tdp_guard_tick(now=10.0))
        await p._offload_call(lambda: p._tdp_guard_tick(now=10.75))
        return loop_tid

    loop_tid = asyncio.run(drive())
    ex.shutdown()
    assert observe_threads
    assert write_threads
    assert loop_tid not in observe_threads
    assert loop_tid not in write_threads
