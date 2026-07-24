"""RPC-level coverage for the custom power-preset wiring in main.py. The store logic
is unit-tested in test_power_presets; this locks the glue (clamp to rails + atomic apply)."""
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
        self._applied = None
        self._levels = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 60},
                "pl2": {"min": 5, "max": 40},
                "pl3": {"min": 5, "max": 50}}

    def set_tdp(self, watts, ac):
        self._applied = watts
        return TdpResult(watts, watts, True, "")

    def set_levels(self, pl1, pl2, pl3, ac):
        self._applied = pl1
        self._levels = (pl1, pl2, pl3)
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied

    _profile = "custom"

    def profile_choices(self):
        return ["low-power", "balanced", "performance", "custom"]

    def read_profile(self):
        return self._profile

    def set_profile(self, mode):
        if mode in self.profile_choices():
            self._profile = mode
            return True
        return False


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "decky", fake)
    from tdp import factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


def test_get_power_presets_fresh_shape(Plugin):
    st = asyncio.run(Plugin().get_power_presets())
    assert st["order"] == ["quiet", "balanced", "turbo"]
    assert st["hidden"] == [] and st["custom"] == {}


def test_create_clamps_watts_to_active_ceiling(Plugin):
    p = Plugin()
    st = asyncio.run(p.create_power_preset(999, "bolt", None))  # on charger, max_ac=60
    cid = st["order"][-1]
    assert st["custom"][cid]["watts"] == 60
    st = asyncio.run(p.create_power_preset(1, "leaf", None))    # below min 5
    cid = st["order"][-1]
    assert st["custom"][cid]["watts"] == 5


def test_crud_and_hide_roundtrip_persists(Plugin):
    p = Plugin()
    st = asyncio.run(p.create_power_preset(12, "bolt", None))
    cid = st["order"][-1]
    st = asyncio.run(p.update_power_preset(cid, 14, "leaf", None, "Emu"))
    assert st["custom"][cid] == {"watts": 14, "icon": "leaf", "name": "Emu",
                                 "boost": {"mode": "estable", "off2": 0, "off3": 0}}
    st = asyncio.run(p.set_power_preset_hidden("quiet", True))
    assert "quiet" in st["hidden"]
    st = asyncio.run(p.move_power_preset("turbo", -1))
    assert st["order"].index("turbo") < st["order"].index("balanced")
    # survives a fresh Plugin (persisted to disk)
    assert asyncio.run(Plugin().get_power_presets())["custom"][cid]["watts"] == 14
    st = asyncio.run(p.delete_power_preset(cid))
    assert cid not in st["custom"]


def test_apply_power_preset_sets_watts_on_scope(Plugin):
    p = Plugin()
    res = asyncio.run(p.apply_power_preset(18, "global", None, None))
    assert res["ok"] is True and res["applied_w"] == 18
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 18


def test_apply_power_preset_with_boost_sets_custom_rails(Plugin):
    p = Plugin()
    res = asyncio.run(p.apply_power_preset(
        20, "global", None, {"mode": "custom", "off2": 8, "off3": 4}))
    assert res["ok"] is True
    st = asyncio.run(p.get_tdp_state())
    assert st["global_boost_mode"] == "custom"
    assert st["global_levels"]["pl2"] == 28 and st["global_levels"]["pl3"] == 32


def test_apply_power_preset_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().apply_power_preset(15, "bogus", None, None))
    assert res["ok"] is False and "unknown scope" in res["detail"]
