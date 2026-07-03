"""RPC-level tests for the GPU-clock controls (get_gpu_clock, set_gpu_clock,
set_gpu_clock_auto). Same bootstrap as test_cpu_rpc, with an injected fake GPU
clock backend so no real amdgpu/i915 node is needed."""
import asyncio
import importlib
import sys
import types


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
        return True


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


def test_set_gpu_clock_auto_releases(tmp_path, monkeypatch):
    p, gpu = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_gpu_clock(1200, 2400))
    st = asyncio.run(p.set_gpu_clock_auto())
    assert st["manual"] is False and gpu._auto is True


def test_gpu_clock_not_reapplied_when_auto(tmp_path, monkeypatch):
    # Not manual → _apply_gpu_clock leaves the GPU alone (don't fight other tools).
    p, gpu = _make_plugin(tmp_path, monkeypatch)
    gpu._cur = (300, 2000)
    p._apply_gpu_clock()
    assert gpu.get() == (300, 2000) and gpu._auto is True
