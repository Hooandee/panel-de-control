import asyncio
import sys
import types

if "decky" not in sys.modules:
    _decky = types.ModuleType("decky")
    _decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    _decky.DECKY_USER = "deck"
    _decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    sys.modules["decky"] = _decky

import main


def _plugin():
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {"disabled_modules": [], "tdp_control_enabled": True, "telemetry_enabled": True}
    p._init = lambda: None
    p._save = lambda: None
    p._reapply_all = lambda on_ac=None: None
    p._sync_sampler = lambda: None
    return p


def test_set_generic_module_persists():
    p = _plugin()
    out = asyncio.run(p.set_ui_module("fans", True))
    assert "fans" in out["disabled"]
    assert p._settings["disabled_modules"] == ["fans"]
    out = asyncio.run(p.set_ui_module("fans", False))
    assert "fans" not in out["disabled"]


def test_set_power_routes_to_tdp_control():
    p = _plugin()
    asyncio.run(p.set_ui_module("power", True))
    assert p._settings["tdp_control_enabled"] is False


def test_set_learning_routes_to_telemetry():
    p = _plugin()
    asyncio.run(p.set_ui_module("learning", True))
    assert p._settings["telemetry_enabled"] is False


def test_unknown_module_is_noop():
    p = _plugin()
    out = asyncio.run(p.set_ui_module("bogus", True))
    assert out["disabled"] == []
    assert p._settings["disabled_modules"] == []


def test_get_ui_modules_reports_full_set():
    p = _plugin()
    p._settings = {"disabled_modules": ["display"], "tdp_control_enabled": False, "telemetry_enabled": True}
    out = asyncio.run(p.get_ui_modules())
    assert set(out["disabled"]) == {"display", "power"}
