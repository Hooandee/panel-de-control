"""RPC-level tests for CPU controls (get_cpu_state, set_smt, set_cpu_boost).

Same Plugin bootstrap as test_battery_rpc: fake decky + fake TDP backend so _init
never touches live hardware, then inject fake SMT/boost controls.
"""
import asyncio
import importlib
import sys
import types


class _FakeToggle:
    def __init__(self, supported=True, on=True):
        self.supported = supported
        self._on = on

    def enabled(self):
        return self._on if self.supported else False

    def set(self, enabled):
        if not self.supported:
            return False
        self._on = bool(enabled)
        return True


class _FakeCores:
    def __init__(self, supported=True, max_cores=8, active=8):
        self.supported = supported
        self.max_cores = max_cores if supported else None
        self._active = active

    def active(self):
        return self._active

    def set(self, n):
        self._active = max(1, min(self.max_cores, int(n)))
        return True


def _make_plugin(tmp_path, monkeypatch, smt=None, boost=None, cores=None):
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

    if smt is not None or boost is not None or cores is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            if smt is not None:
                self._smt = smt
            if boost is not None:
                self._boost = boost
            if cores is not None:
                self._cores = cores

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin()


def test_get_cpu_state_shape(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle())
    st = asyncio.run(p.get_cpu_state())
    assert "chip" in st
    assert st["smt"] == {"supported": True, "enabled": True}
    assert st["boost"] == {"supported": True, "enabled": True}
    assert "cores" in st and "max_khz" in st


def test_set_smt_toggles_and_persists(tmp_path, monkeypatch):
    smt = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, smt=smt, boost=_FakeToggle())
    st = asyncio.run(p.set_smt(False))
    assert smt.enabled() is False
    assert st["smt"]["enabled"] is False
    # persisted
    p2 = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(on=True), boost=_FakeToggle())
    p2._init()
    p2._apply_cpu()  # startup re-applies persisted state
    assert p2._smt.enabled() is False


def test_set_boost_toggles(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=boost)
    asyncio.run(p.set_cpu_boost(False))
    assert boost.enabled() is False


def test_set_active_cores_persists_and_reapplies(tmp_path, monkeypatch):
    cores = _FakeCores(max_cores=8, active=8)
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(), cores=cores)
    st = asyncio.run(p.set_active_cores(4))
    assert cores.active() == 4
    assert st["active_cores"] == 4 and st["max_cores"] == 8 and st["cores_supported"] is True
    # persisted → startup re-applies
    p2 = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
                      cores=_FakeCores(max_cores=8, active=8))
    p2._init()
    p2._apply_cpu()
    assert p2._cores.active() == 4


def test_cores_unsupported_hides(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
                     cores=_FakeCores(supported=False))
    st = asyncio.run(p.get_cpu_state())
    assert st["cores_supported"] is False and st["active_cores"] is None


def test_unsupported_controls_degrade(tmp_path, monkeypatch):
    p = _make_plugin(
        tmp_path, monkeypatch,
        smt=_FakeToggle(supported=False), boost=_FakeToggle(supported=False),
    )
    st = asyncio.run(p.set_smt(False))
    assert st["smt"]["supported"] is False
    st2 = asyncio.run(p.set_cpu_boost(False))
    assert st2["boost"]["supported"] is False
