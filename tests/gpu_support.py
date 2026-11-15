import sys
import types
from main_harness import load_main


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

    def capture_state(self):
        return {"auto": self._auto, "window": self._cur}

    def restore_state(self, state):
        if state["auto"]:
            return self.set_auto()
        return self.set(*state["window"])

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

    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)

    fake_gpu = gpu if gpu is not None else _FakeGpuClock()
    original_init = main.Plugin._init

    def patched_init(self):
        original_init(self)
        self._gpu_clock = fake_gpu

    monkeypatch.setattr(main.Plugin, "_init", patched_init)
    return main.Plugin(), fake_gpu
