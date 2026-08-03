"""RPC-level tests for the GPU-clock controls (get_gpu_clock, set_gpu_clock,
set_gpu_clock_auto). Same bootstrap as test_cpu_rpc, with an injected fake GPU
clock backend so no real amdgpu/i915 node is needed."""
import asyncio
import importlib
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor


class _FakeGpuClock:
    def __init__(self, supported=True):
        self.supported = supported
        self._cur = (300, 2000)
        self._auto = True

    def get_range(self):
        return (200, 2700) if self.supported else None

    def get(self):
        return self._cur if self.supported else None

    def set(self, lo, hi):
        self._cur = (int(lo), int(hi))
        self._auto = False
        return True

    def set_auto(self):
        self._auto = True
        self._cur = (200, 2700)
        return True

    backend = "fake"

    def diagnostics(self):
        return {
            "backend": self.backend,
            "supported": self.supported,
            "range": {"min_mhz": 200, "max_mhz": 2700} if self.supported else None,
            "applied": (
                {"min_mhz": self._cur[0], "max_mhz": self._cur[1]}
                if self.supported else None
            ),
            "last_operation": None,
        }


class _RejectingGpuClock(_FakeGpuClock):
    def set(self, lo, hi):
        return False


class _BlockingFirstGpuClock(_FakeGpuClock):
    def __init__(self):
        super().__init__()
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self._calls = 0
        self._calls_lock = threading.Lock()

    def set(self, lo, hi):
        with self._calls_lock:
            self._calls += 1
            call = self._calls
        if call == 1:
            self.first_started.set()
            assert self.release_first.wait(timeout=2)
        return super().set(lo, hi)


class _TransientAutoFailureGpuClock(_FakeGpuClock):
    def __init__(self, failures):
        super().__init__()
        self.failures = failures
        self.auto_calls = 0

    def set_auto(self):
        self.auto_calls += 1
        if self.auto_calls <= self.failures:
            return False
        return super().set_auto()


def _make_plugin(tmp_path, monkeypatch, gpu=None):
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
        supports_levels = False
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

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

    fake_gpu = gpu if gpu is not None else _FakeGpuClock()
    original_init = main.Plugin._init

    def patched_init(self):
        original_init(self)
        self._gpu_clock = fake_gpu

    monkeypatch.setattr(main.Plugin, "_init", patched_init)
    return main.Plugin(), fake_gpu


def test_get_gpu_clock_shape(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.get_gpu_clock())
    assert st["supported"] is True
    assert st["range_min"] == 200 and st["range_max"] == 2700
    assert st["manual"] is False


def test_set_gpu_clock_pins_and_persists(tmp_path, monkeypatch):
    p, gpu = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_gpu_clock(1200, 2400))
    assert gpu.get() == (1200, 2400)
    assert st["manual"] is True and st["min"] == 1200 and st["max"] == 2400
    # persisted → startup re-applies
    p2, gpu2 = _make_plugin(tmp_path, monkeypatch)
    p2._init()
    p2._apply_gpu_clock()
    assert gpu2.get() == (1200, 2400)


def test_rejected_gpu_clock_does_not_persist(tmp_path, monkeypatch):
    p, gpu = _make_plugin(tmp_path, monkeypatch, _RejectingGpuClock())
    st = asyncio.run(p.set_gpu_clock(1200, 2400))
    assert st["manual"] is False
    assert st["status"] == "rejected"
    assert st["requested_min"] == 1200
    assert st["applied_min"] == 300

    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_gpu_clock())["manual"] is False


def test_set_gpu_clock_auto_releases(tmp_path, monkeypatch):
    p, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_gpu_clock(1200, 2400))
    st = asyncio.run(p.set_gpu_clock_auto())
    assert st["manual"] is False and gpu._auto is True


def test_gpu_clock_not_reapplied_when_auto(tmp_path, monkeypatch):
    # Not manual → _apply_gpu_clock leaves the GPU alone (don't fight other tools).
    p, gpu = _make_plugin(tmp_path, monkeypatch)
    p._init()  # load settings so the module gate in _apply_gpu_clock can read them
    gpu._cur = (300, 2000)
    p._apply_gpu_clock()
    assert gpu.get() == (300, 2000) and gpu._auto is True


def test_lifecycle_gpu_reapply_cannot_be_overwritten_by_older_rpc(
    tmp_path, monkeypatch
):
    gpu = _BlockingFirstGpuClock()
    p, _ = _make_plugin(tmp_path, monkeypatch, gpu)
    p._apply_executor = ThreadPoolExecutor(max_workers=1)

    async def scenario():
        older_rpc = asyncio.create_task(p.set_gpu_clock(600, 1200))
        await asyncio.sleep(0)
        assert gpu.first_started.wait(timeout=1)

        p._tdp_profiles.set_gpu_clock("global", True, 1400, 2200)
        p._apply_gpu_clock()

        gpu.release_first.set()
        await older_rpc
        await p._drain_offloaded()

    try:
        asyncio.run(scenario())
    finally:
        gpu.release_first.set()
        p._apply_executor.shutdown(wait=True)

    assert gpu.get() == (1400, 2200)


def test_disabling_power_module_releases_manual_gpu_clock(
    tmp_path, monkeypatch
):
    plugin, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(plugin.set_gpu_clock(1_200, 2_400))

    assert gpu._auto is False
    result = asyncio.run(plugin.set_ui_module("power", True))

    assert "power" in result["disabled"]
    assert gpu._auto is True
    assert gpu.get() == gpu.get_range()


def test_unload_releases_manual_gpu_clock(tmp_path, monkeypatch):
    plugin, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(plugin.set_gpu_clock(1_200, 2_400))

    asyncio.run(plugin._unload())

    assert gpu._auto is True
    assert gpu.get() == gpu.get_range()


def test_gpu_handoff_retries_transient_auto_failure(tmp_path, monkeypatch):
    gpu = _TransientAutoFailureGpuClock(failures=2)
    plugin, _ = _make_plugin(tmp_path, monkeypatch, gpu)
    asyncio.run(plugin.set_gpu_clock(1_200, 2_400))

    released = asyncio.run(plugin._release_gpu_clock("unload"))

    assert released is True
    assert gpu.auto_calls == 3
    assert gpu._auto is True
    assert gpu.get() == gpu.get_range()


def test_gpu_shutdown_handoff_cannot_be_overwritten_by_late_rpc(
    tmp_path, monkeypatch
):
    plugin, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(plugin.set_gpu_clock(1_200, 2_400))
    plugin._gpu_shutdown = True

    async def yielding_offload(fn):
        await asyncio.sleep(0)
        return fn()

    plugin._offload_call = yielding_offload

    async def drive():
        released, _state = await asyncio.gather(
            plugin._release_gpu_clock("unload"),
            plugin.set_gpu_clock(1_400, 2_200),
        )
        return released

    assert asyncio.run(drive()) is True
    assert gpu._auto is True
    assert gpu.get() == gpu.get_range()


def test_manual_gpu_store_failure_restores_auto_hardware_and_memory(
    tmp_path, monkeypatch
):
    plugin, gpu = _make_plugin(tmp_path, monkeypatch)
    plugin._init()

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(plugin._tdp_profiles, "_save", fail_save)

    state = asyncio.run(plugin.set_gpu_clock(900, 1_800))

    assert gpu._auto is True
    assert gpu.get() == gpu.get_range()
    assert plugin._tdp_profiles.gpu_clock(None)["manual"] is False
    assert state["status"] == "rejected"
    assert state["reason"] == "store_write_failed"


def test_auto_gpu_store_failure_restores_previous_manual_window(
    tmp_path, monkeypatch
):
    plugin, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(plugin.set_gpu_clock(1_200, 2_400))

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(plugin._tdp_profiles, "_save", fail_save)

    state = asyncio.run(plugin.set_gpu_clock_auto())

    assert gpu._auto is False
    assert gpu.get() == (1_200, 2_400)
    assert plugin._tdp_profiles.gpu_clock(None) == {
        "manual": True,
        "min": 1_200,
        "max": 2_400,
    }
    assert state["status"] == "rejected"
    assert state["reason"] == "store_write_failed"
