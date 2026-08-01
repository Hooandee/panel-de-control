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

from controllers.coordinator import ControllerCoordinator
from controllers.operations import OperationResult


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

def test_reapply_all_offloads_tdp_fans_and_color(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    rec = _RecordingExecutor()
    p._apply_executor = rec

    async def _run():
        p._reapply_all()  # sync, but under a running loop

    asyncio.run(_run())
    # tdp + fans + color offloaded; charge/cpu/gpu-clock stay inline (sysfs); hdr only
    # offloads when it's enabled+supported (off by default here).
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
    p._restore_hhd_tdp = lambda: events.append("handoff")

    async def run():
        p._apply_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        p._offload(block_executor)
        while not blocker_started.is_set():
            await asyncio.sleep(0)
        p._schedule_tdp_apply("queued-before-unload")
        unload = asyncio.create_task(p._unload())
        await asyncio.sleep(0)
        release_blocker.set()
        await unload

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


class _LifecycleController:
    manager = "inputplumber"

    def __init__(self, profile, statuses=None, write_ok=True):
        self.profile = profile
        self.statuses = statuses or {}
        self.write_ok = write_ok
        self.events = []

    def set_button(self, source, targets, scope, appid):
        return {"last_apply": self.write_ok}

    def set_vibration(self, patch, scope, appid):
        return {"vibration": {"last_apply": self.write_ok}}

    def effective_profile(self, appid):
        return self.profile

    def owns_loaded_profile(self):
        return True

    def apply_component(self, component, desired, appid, generation):
        self.events.append((component, appid))
        status = self.statuses.get(component, "applied")
        return OperationResult(
            component, status,
            "apply_failed" if status == "failed" else None,
            self.manager, generation, appid, desired,
            desired if status == "applied" else None,
        )

    def wait_ready(self, appid, generation):
        self.events.append(("wait_ready", appid))
        return True

    def cancel_transients(self, reason):
        self.events.append(("cancel", reason))

    def clear_translated_state(self):
        self.events.append(("clear", None))
        return True

    def restore_external(self):
        self.events.append(("restore_external", None))
        return True


def _controller_for(p, profile, statuses=None, write_ok=True):
    backend = _LifecycleController(profile, statuses, write_ok)
    p._controller_backend = backend
    p._controller_coordinator = ControllerCoordinator(backend)
    return backend


def test_failed_controller_write_remains_pending_for_lifecycle_retry(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    _controller_for(
        p,
        {"virtual_controller": {}, "buttons": {}, "vibration": {"value": 40}},
        write_ok=False,
    )
    p._current_appid = "42"

    asyncio.run(p.set_controller_vibration(
        {"value": 40}, scope="game", appid="42"
    ))

    assert p._controller_coordinator.snapshot()["components"] == {}


def test_component_results_remain_independent_after_button_write(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    backend = _controller_for(
        p,
        {
            "virtual_controller": {},
            "buttons": {"LeftPaddle1": [{"gamepad": "South"}]},
            "vibration": {"value": 40},
        },
        statuses={"vibration": "failed"},
    )
    p._current_appid = "42"

    asyncio.run(p.set_controller_button(
        "LeftPaddle1", [{"gamepad": "South"}],
        scope="game", appid="42",
    ))

    components = p._controller_coordinator.snapshot()["components"]
    assert components["buttons"]["status"] == "applied"
    assert components["vibration"]["status"] == "failed"
    assert ("vibration", "42") in backend.events


def test_unload_reconciles_global_controller_before_handoff(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    backend = _controller_for(p, {
        "virtual_controller": {}, "buttons": {},
        "vibration": {"value": 100},
    })
    p._restore_fans_safe = lambda: None
    p._restore_color_safe = lambda: None
    p._restore_audio_safe = lambda: None
    p._restore_hhd_tdp = lambda: backend.events.append(("handoff", None))

    asyncio.run(p._unload())

    assert ("virtual_controller", None) in backend.events
    assert backend.events[-1] == ("handoff", None)


def test_forced_controller_reapply_runs_same_desired_profile(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    profile = {
        "virtual_controller": {}, "buttons": {},
        "vibration": {"value": 40},
    }
    backend = _controller_for(p, profile)
    p._current_appid = "42"

    p._reapply_controller(force=True)
    p._reapply_controller(force=True)

    assert backend.events.count(("vibration", "42")) == 2


def test_forced_startup_restores_owned_profile_with_empty_global(
    tmp_path, monkeypatch
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    backend = _controller_for(p, {
        "virtual_controller": {}, "buttons": {}, "vibration": {},
    })
    p._current_appid = None

    p._reapply_controller(force=True)

    assert ("buttons", None) in backend.events


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
    p._restore_hhd_tdp = handoff
    monkeypatch.setattr(
        importlib.import_module("main").fan_expose,
        "remove_conf",
        lambda: None,
    )

    asyncio.run(p._uninstall())
    assert events == ["handoff"]


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
