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


def _plugin(disabled=None, telemetry=True, tdp_control=True):
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {
        "disabled_modules": list(disabled or []),
        "telemetry_enabled": telemetry,
        "tdp_control_enabled": tdp_control,
    }
    return p


def test_learning_gate_true_when_consumer_present():
    assert _plugin(telemetry=True)._learning_active() is True


def test_learning_gate_false_when_both_consumers_off():
    p = _plugin(disabled=["fans"], tdp_control=False, telemetry=True)
    assert p._learning_active() is False


def test_learning_gate_false_when_telemetry_off():
    assert _plugin(telemetry=False)._learning_active() is False


class _FakeChargeLimit:
    supported = True

    def __init__(self):
        self.calls = []

    def set(self, p):
        self.calls.append(("set", p))

    def disable(self):
        self.calls.append(("disable",))


def _plugin_cl(disabled=None):
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {
        "disabled_modules": list(disabled or []),
        "tdp_control_enabled": True,
        "telemetry_enabled": True,
        "charge_limit_enabled": True,
        "charge_limit_percent": 80,
    }
    p._charge_limit = _FakeChargeLimit()
    return p


def test_charge_limit_released_when_system_disabled():
    # Disabling the System module steps aside: release the cap, don't keep limiting.
    p = _plugin_cl(disabled=["system"])
    p._apply_charge_limit()
    assert p._charge_limit.calls == [("disable",)]


def test_charge_limit_applied_when_system_enabled():
    p = _plugin_cl()
    p._apply_charge_limit()
    assert ("set", 80) in p._charge_limit.calls


class _FakeToggle:
    def __init__(self, supported=True, max_cores=8):
        self.supported = supported
        self.max_cores = max_cores
        self.calls = []

    def set(self, v):
        self.calls.append(v)


def _plugin_cpu(disabled=None):
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {
        "disabled_modules": list(disabled or []),
        "tdp_control_enabled": True,
        "telemetry_enabled": True,
    }
    p._cores = _FakeToggle(max_cores=8)
    p._smt = _FakeToggle()
    p._boost = _FakeToggle()
    return p


def test_cpu_released_to_defaults_when_system_disabled():
    # All cores online, SMT on, boost on — hand the CPU back, don't leave it parked.
    p = _plugin_cpu(disabled=["system"])
    p._apply_cpu()
    assert p._cores.calls == [8]
    assert p._smt.calls == [True]
    assert p._boost.calls == [True]


def test_collect_sample_none_when_learning_inactive():
    # Both consumers off → learning blocked → never record, even in a game.
    p = main.Plugin.__new__(main.Plugin)
    p._settings = {"disabled_modules": ["fans"], "tdp_control_enabled": False, "telemetry_enabled": True}
    p._current_appid = "123"
    assert p._collect_sample() is None


def test_disabling_power_module_hands_hhd_back():
    import asyncio

    p = main.Plugin.__new__(main.Plugin)
    p._settings = {
        "disabled_modules": [],
        "tdp_control_enabled": True,
        "telemetry_enabled": True,
        "hhd_tdp_prev": True,
    }
    p._init = lambda: None
    p._save = lambda: None
    p._reapply_all = lambda *a, **k: None
    p._sync_sampler = lambda: None

    async def _offload(fn):
        return fn()

    p._offload_call = _offload

    calls = []
    orig = main.controller_hhd.set_tdp_enable
    main.controller_hhd.set_tdp_enable = lambda v: calls.append(v)
    try:
        res = asyncio.run(p.set_ui_module("power", True))
    finally:
        main.controller_hhd.set_tdp_enable = orig

    assert calls == [True]  # HHD's TDP handed back
    assert p._settings["hhd_tdp_prev"] is None  # and the marker cleared
    assert "power" in res["disabled"]
