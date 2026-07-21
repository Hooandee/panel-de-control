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


def _plugin(disabled=None, tdp_control=True, telemetry=True):
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {
        "disabled_modules": list(disabled or []),
        "tdp_control_enabled": tdp_control,
        "telemetry_enabled": telemetry,
    }
    return p


def test_tab_enabled_by_default():
    p = _plugin()
    assert p._module_enabled("fans") is True
    assert p._module_enabled("system") is True


def test_generic_tab_disabled():
    p = _plugin(disabled=["fans"])
    assert p._module_enabled("fans") is False


def test_power_maps_to_tdp_control():
    assert _plugin(tdp_control=False)._module_enabled("power") is False
    assert _plugin(tdp_control=True)._module_enabled("power") is True


def test_learning_maps_to_telemetry():
    assert _plugin(telemetry=False)._module_enabled("learning") is False


def test_autotdp_cascades_from_power():
    assert _plugin(tdp_control=False)._module_enabled("autoTdp") is False


def test_fancontrol_cascades_from_fans():
    assert _plugin(disabled=["fans"])._module_enabled("fanControl") is False


def test_learning_requires_power_or_fans():
    p = _plugin(disabled=["fans"], tdp_control=False, telemetry=True)
    assert p._module_enabled("learning") is False
    assert _plugin(disabled=["fans"], tdp_control=True)._module_enabled("learning") is True
    assert _plugin(disabled=[], tdp_control=False)._module_enabled("learning") is True


def test_user_disabled_all_folds_native_settings():
    p = _plugin(disabled=["display"], tdp_control=False, telemetry=False)
    got = set(p._user_disabled_all())
    assert got == {"display", "power", "learning"}
