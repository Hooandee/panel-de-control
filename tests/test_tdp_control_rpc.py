"""RPC-level coverage for the TDP control master switch + HHD take/release.

Locks the glue in main.py: the conflict readout, taking control from HHD
(reversible, saving the previous value), the master switch gating every TDP
write, and restoring HHD on release / lifecycle teardown. Pure logic lives in
test_hhd_tdp_enable / the frontend conflict tests; this covers the wiring.
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

    def __init__(self):
        self.set_levels_calls = 0
        self._applied = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 35}}

    def set_levels(self, pl1, pl2, pl3, ac):
        self.set_levels_calls += 1
        self._applied = pl1
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied


class FakeFan:
    supported = True
    name = "fake-fan"

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255, "fans": []}

    def apply_curve_all(self, points):
        pass

    def set_auto(self, points):
        pass

    def restore_auto(self):
        pass


class FakeHHD:
    """Stand-in for the controllers.hhd module functions."""
    def __init__(self, value=True):
        self.value = value

    def set(self, v):
        self.value = v

    def current_tdp_enable(self, root="/"):
        return self.value

    def set_tdp_enable(self, enabled, root="/"):
        self.value = bool(enabled)
        return self.value


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
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
    monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


@pytest.fixture
def fake_hhd(monkeypatch):
    import main as main_mod
    fh = FakeHHD()
    monkeypatch.setattr(main_mod.controller_hhd, "current_tdp_enable", fh.current_tdp_enable)
    monkeypatch.setattr(main_mod.controller_hhd, "set_tdp_enable", fh.set_tdp_enable)
    return fh


# ---------------------------------------------------------------------------
# Conflict readout
# ---------------------------------------------------------------------------

def test_conflict_reports_hhd_managing(Plugin, fake_hhd):
    import main as main_mod
    p = Plugin()
    p._init()
    p._controller_backend.manager = main_mod.controller_detect.HHD
    fake_hhd.set(True)
    out = asyncio.run(p.get_tdp_conflict())
    assert out == {"hhd_present": True, "hhd_managing": True}


def test_conflict_no_hhd_present(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    # Default test backend manager is NONE → we never poke HHD's API.
    out = asyncio.run(p.get_tdp_conflict())
    assert out["hhd_present"] is False
    assert out["hhd_managing"] is False


# ---------------------------------------------------------------------------
# Take / release control (reversible, saves previous value)
# ---------------------------------------------------------------------------

def test_take_and_release_restores_hhd(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    out = asyncio.run(p.take_tdp_control())
    assert out["ok"] is True
    assert fake_hhd.value is False                 # HHD's TDP handed to us
    assert p._settings["hhd_tdp_prev"] is True     # remembered for restore
    asyncio.run(p.release_tdp_control())
    assert fake_hhd.value is True                  # restored
    assert p._settings["hhd_tdp_prev"] is None


def test_take_when_hhd_unreachable_is_honest(Plugin, monkeypatch):
    import main as main_mod
    monkeypatch.setattr(main_mod.controller_hhd, "current_tdp_enable",
                        lambda root="/": None)
    p = Plugin()
    p._init()
    out = asyncio.run(p.take_tdp_control())
    assert out["ok"] is False
    assert p._settings["hhd_tdp_prev"] is None


def test_take_does_not_overwrite_saved_prev(Plugin, fake_hhd):
    # Already off (someone else) → don't record False as the value to restore to.
    p = Plugin()
    p._init()
    p._settings["hhd_tdp_prev"] = True   # a prior take is already remembered
    fake_hhd.set(False)
    asyncio.run(p.take_tdp_control())
    assert p._settings["hhd_tdp_prev"] is True   # unchanged


def test_release_noop_when_never_taken(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    asyncio.run(p.release_tdp_control())
    assert fake_hhd.value is True          # untouched — nothing to restore
    assert p._settings["hhd_tdp_prev"] is None


# ---------------------------------------------------------------------------
# Master switch gating
# ---------------------------------------------------------------------------

def test_reapply_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    res = p._reapply_tdp()
    assert p._tdp_backend.set_levels_calls == 0
    assert res.ok is True
    assert res.detail == "tdp-control-disabled"


def test_reapply_writes_when_control_enabled(Plugin):
    p = Plugin()
    p._init()
    p._tdp_backend.set_levels_calls = 0
    p._reapply_tdp()
    assert p._tdp_backend.set_levels_calls == 1


def test_set_tdp_watts_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    out = asyncio.run(p.set_tdp_watts(20, "global"))
    assert out["ok"] is False
    assert p._tdp_backend.set_levels_calls == 0


def test_set_tdp_levels_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    out = asyncio.run(p.set_tdp_levels(5, 10, "global"))
    assert out["ok"] is False
    assert p._tdp_backend.set_levels_calls == 0


def test_set_auto_tdp_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    asyncio.run(p.set_auto_tdp(True, "global"))
    assert p._tdp_backend.set_levels_calls == 0


# ---------------------------------------------------------------------------
# Master-switch RPC: OFF restores HHD, ON re-applies our setpoint
# ---------------------------------------------------------------------------

def test_set_control_enabled_off_restores_hhd(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    asyncio.run(p.take_tdp_control())
    assert fake_hhd.value is False
    assert asyncio.run(p.set_tdp_control_enabled(False)) is False
    assert fake_hhd.value is True                 # handed back on release
    assert p._settings["tdp_control_enabled"] is False


def test_set_control_enabled_on_reapplies(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    assert asyncio.run(p.set_tdp_control_enabled(True)) is True
    assert p._tdp_backend.set_levels_calls == 1


def test_get_control_enabled_default_true(Plugin):
    p = Plugin()
    assert asyncio.run(p.get_tdp_control_enabled()) is True


# ---------------------------------------------------------------------------
# Persisted "seen" flags (durable across reboot; CEF localStorage is not)
# ---------------------------------------------------------------------------

def test_seen_flag_setters_persist(Plugin):
    p = Plugin()
    p._init()
    assert asyncio.run(p.set_seen_autotdp_notice(True)) is True
    assert asyncio.run(p.set_seen_tdp_conflict_takeover(True)) is True
    assert p._settings["seen_autotdp_notice"] is True
    assert p._settings["seen_tdp_conflict_takeover"] is True
    # a fresh instance reading the same store sees them
    p2 = Plugin()
    p2._init()
    assert p2._settings["seen_autotdp_notice"] is True
    assert p2._settings["seen_tdp_conflict_takeover"] is True


# ---------------------------------------------------------------------------
# Lifecycle restore (good citizen: hand HHD back)
# ---------------------------------------------------------------------------

def test_unload_restores_hhd(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    asyncio.run(p.take_tdp_control())
    assert fake_hhd.value is False
    asyncio.run(p._unload())
    assert fake_hhd.value is True
