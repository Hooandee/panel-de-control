"""RPC-level tests for battery state + charge limit.

Bootstraps a real Plugin with a fake decky module and a fake TDP backend (so
_init never touches live hardware), then injects a fake charge-limit backend.
"""
import asyncio
import importlib
import sys
import types


def _make_plugin(tmp_path, monkeypatch, charge_limit=None):
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

    if charge_limit is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            self._charge_limit = charge_limit

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin()


class _FakeChargeLimit:
    adjustable = True

    def __init__(self, supported=True):
        self.supported = supported
        self.value = 100

    def get(self):
        return self.value if self.supported else None

    def range(self):
        return (20, 100)

    def set(self, percent):
        if not self.supported:
            return False
        self.value = int(percent)
        return True

    def disable(self):
        if not self.supported:
            return False
        self.value = 100  # ASUS-like: 100 = no cap
        return True


def test_get_battery_state_shape(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())
    state = asyncio.run(p.get_battery_state())
    assert "battery" in state and "charge_limit" in state
    cl = state["charge_limit"]
    assert cl["supported"] is True
    assert cl["enabled"] is False
    assert cl["percent"] == 80
    assert cl["min"] == 20 and cl["max"] == 100


def test_set_charge_limit_enables_and_applies(tmp_path, monkeypatch):
    cl_backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=cl_backend)
    result = asyncio.run(p.set_charge_limit(True, 70))
    assert result["enabled"] is True
    assert result["percent"] == 70
    assert cl_backend.value == 70  # applied to hardware


def test_disable_writes_no_cap(tmp_path, monkeypatch):
    cl_backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=cl_backend)
    asyncio.run(p.set_charge_limit(True, 60))
    assert cl_backend.value == 60
    asyncio.run(p.set_charge_limit(False, 60))
    assert cl_backend.value == 100  # disabled -> firmware default


def test_set_charge_limit_persists(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())
    asyncio.run(p.set_charge_limit(True, 65))
    # a fresh plugin over the same settings dir reloads the saved values and, at
    # startup, re-applies the persisted limit to hardware (as _reapply_all does).
    cl2 = _FakeChargeLimit()
    p2 = _make_plugin(tmp_path, monkeypatch, charge_limit=cl2)
    p2._init()
    p2._apply_charge_limit()
    assert cl2.value == 65  # persisted limit re-applied to hardware
    cl = asyncio.run(p2.get_battery_state())["charge_limit"]
    assert cl["enabled"] is True and cl["percent"] == 65


def test_unsupported_charge_limit_degrades(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit(supported=False))
    result = asyncio.run(p.set_charge_limit(True, 70))
    assert result["supported"] is False
