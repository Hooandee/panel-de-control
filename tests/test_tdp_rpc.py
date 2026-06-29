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
        return TdpLimits(min_w=5, default_w=15, max_w=25, max_ac_w=30)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 30},
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
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


def test_get_tdp_state_shape(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supported"] is True and st["backend"] == "fake"
    assert st["limits"] == {"min": 5, "default": 15, "max": 25, "max_ac": 30}
    assert "on_ac" in st and "watts" in st and "applied_w" in st
    assert "global_watts" in st and isinstance(st["global_watts"], int)


def test_set_tdp_watts_global_clamps_persists_applies(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(99, "global"))
    assert res["ok"] is True and res["applied_w"] == 30  # clamped to max_ac
    st = asyncio.run(p.get_tdp_state())
    assert st["watts"] == 30
    # survives reload (persisted)
    assert asyncio.run(Plugin().get_tdp_state())["watts"] == 30


def test_per_game_profile_overrides_global(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.create_game_profile("42"))
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_tdp_watts(10, "game", "42"))
    st = asyncio.run(p.get_tdp_state())
    assert st["watts"] == 10
    assert st["global_watts"] == 20
    asyncio.run(p.set_current_game(None))
    assert asyncio.run(p.get_tdp_state())["watts"] == 20


def test_set_tdp_watts_game_without_appid_falls_back_to_global(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(20, "game", None))  # appid missing
    assert res["ok"] is True  # did not raise
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 20


def test_set_tdp_watts_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_watts(15, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_state_exposes_advanced_fields(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supports_advanced"] is True
    assert st["level_limits"]["pl2"] == {"min": 5, "max": 40}
    assert st["auto"] is True  # fresh profile is auto
    assert set(st["levels"]) == {"pl1", "pl2", "pl3"}
    assert "global_levels" in st and "global_auto" in st


def test_set_tdp_levels_goes_manual_and_clamps(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))      # pl1 = 20, still auto
    res = asyncio.run(p.set_tdp_levels(8, 4, "global"))  # SPPT +8, FPPT +4
    assert res["ok"] is True
    st = asyncio.run(p.get_tdp_state())
    assert st["auto"] is False
    assert st["levels"]["pl2"] == 28 and st["levels"]["pl3"] == 32


def test_set_tdp_levels_clamps_to_rail_max(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(40, 40, "global"))  # 20+40=60 -> pl2 clamps to 40
    st = asyncio.run(p.get_tdp_state())
    # pl3: 20+40+40=100 -> clamped to rail max 50
    assert st["levels"]["pl2"] == 40 and st["levels"]["pl3"] == 50


def test_reset_tdp_auto_reverts(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))
    assert asyncio.run(p.get_tdp_state())["auto"] is False
    asyncio.run(p.reset_tdp_auto("global"))
    assert asyncio.run(p.get_tdp_state())["auto"] is True


def test_set_tdp_watts_preserves_manual_margins(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(17, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))   # manual: pl2=25, pl3=29
    asyncio.run(p.set_tdp_watts(22, "global"))      # raise pl1, keep margins
    st = asyncio.run(p.get_tdp_state())
    assert st["auto"] is False
    assert st["levels"]["pl2"] == 30 and st["levels"]["pl3"] == 34


def test_set_tdp_levels_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_levels(8, 4, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_reset_tdp_auto_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().reset_tdp_auto("bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]
