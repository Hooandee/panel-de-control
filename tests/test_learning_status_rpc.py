"""RPC coverage for get_learning_status (the persistent learning banner's flags).

Pure banner-state logic lives in the frontend (src/learning/logic.test.ts); this
locks the backend snapshot: telemetry opt-in + real per-device capabilities,
including the honest fan-Null (read-only) path.
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

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 35}}

    def set_levels(self, pl1, pl2, pl3, ac):
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return None


class FakeFan:
    name = "fake-fan"

    def __init__(self, supported=True):
        self.supported = supported

    def read_state(self):
        return {"supported": self.supported, "source": "fake", "pwm_max": 255, "fans": []}

    def restore_auto(self):
        pass


def _make_plugin(tmp_path, monkeypatch, fan_supported=True):
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
    monkeypatch.setattr(fan_control, "select_fan_backend",
                        lambda device, **kw: FakeFan(supported=fan_supported))
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin()


def test_learning_status_both_supported_telemetry_default_on(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, fan_supported=True)
    st = asyncio.run(p.get_learning_status())
    assert st == {"telemetry_enabled": True, "tdp_supported": True, "fan_supported": True}


def test_learning_status_fan_null_reports_false(tmp_path, monkeypatch):
    # Device whose fan backend can't write curves (e.g. MSI Claw Null) → honest False.
    p = _make_plugin(tmp_path, monkeypatch, fan_supported=False)
    st = asyncio.run(p.get_learning_status())
    assert st["fan_supported"] is False
    assert st["tdp_supported"] is True


def test_learning_status_reflects_telemetry_opt_out(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_telemetry_enabled(False))
    st = asyncio.run(p.get_learning_status())
    assert st["telemetry_enabled"] is False


@pytest.mark.parametrize("enabled", [True, False])
def test_learning_status_telemetry_roundtrip(tmp_path, monkeypatch, enabled):
    p = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_telemetry_enabled(enabled))
    st = asyncio.run(p.get_learning_status())
    assert st["telemetry_enabled"] is enabled
