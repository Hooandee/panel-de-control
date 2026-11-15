import asyncio

import pytest

from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult
from main_harness import fake_decky, load_main


class MenuFloorBackend(TDPBackend):
    supported = True
    supports_levels = True
    name = "fake"
    menu_rail_floors = {"pl2": 15, "pl3": 20}

    def __init__(self):
        self._levels = (15, 15, 15)

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=33, max_ac_w=33)

    def level_limits(self):
        return {
            "pl1": {"min": 5, "max": 33},
            "pl2": {"min": 5, "max": 33},
            "pl3": {"min": 5, "max": 35},
        }

    def set_tdp(self, watts, ac):
        return self.set_levels(watts, watts, watts, ac)

    def set_levels(self, pl1, pl2, pl3, ac):
        self._levels = (int(pl1), int(pl2), int(pl3))
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._levels[0]

    def observe(self):
        pl1, pl2, pl3 = self._levels
        return TdpObservation(
            readable=True,
            surfaces={
                self.name: {
                    "pl1": RailReading(pl1, 5, 33),
                    "pl2": RailReading(pl2, 5, 33),
                    "pl3": RailReading(pl3, 5, 35),
                },
            },
        )


class PlainBackend(MenuFloorBackend):
    menu_rail_floors = {}


def _plugin(tmp_path, monkeypatch, backend_cls):
    fake_decky(monkeypatch, tmp_path)
    import tdp.factory as factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: backend_cls())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": False)
    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": False, raising=False)
    plugin = main.Plugin()
    plugin._init()
    plugin._tdp_profiles.set_pl1("global", 5)
    return plugin


def test_menu_floors_never_exceed_the_rail_ceiling(tmp_path, monkeypatch):
    class LowCeiling(MenuFloorBackend):
        def level_limits(self):
            return {
                "pl1": {"min": 5, "max": 12},
                "pl2": {"min": 5, "max": 12},
                "pl3": {"min": 5, "max": 18},
            }

    plugin = _plugin(tmp_path, monkeypatch, LowCeiling)

    command = plugin._capture_tdp_command("lifecycle", on_ac=False)

    assert command.safe_bounds["pl2"]["min"] <= command.safe_bounds["pl2"]["max"]
    assert command.safe_bounds["pl3"]["min"] <= command.safe_bounds["pl3"]["max"]


def test_manual_menu_toggle_reapplies_power_both_ways(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    plugin._set_current_appid("42")
    reasons = []
    monkeypatch.setattr(
        plugin,
        "_schedule_tdp_apply",
        lambda reason, on_ac=None: reasons.append(reason),
    )

    asyncio.run(plugin.set_ui_active(True))
    asyncio.run(plugin.set_ui_active(True))
    asyncio.run(plugin.set_ui_active(False))

    assert reasons == ["menu-floor", "menu-floor"]


@pytest.mark.parametrize("in_game", [False, True])
def test_menu_floor_state_is_reported_in_tdp_diagnostics(tmp_path, monkeypatch, in_game):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    if in_game:
        plugin._set_current_appid("42")

    assert plugin._tdp_diagnostics()["menu_rail_floors"] == {
        "floors": {"pl2": 15, "pl3": 20},
        "active": not in_game,
    }


@pytest.mark.parametrize("in_game", [False, True])
def test_tdp_ownership_says_when_the_menu_floor_holds_the_boost_rails(
    tmp_path, monkeypatch, in_game,
):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    if in_game:
        plugin._set_current_appid("42")

    ownership = plugin._tdp_ownership_state(plugin._tdp_backend.observe())

    assert ownership["menu_floor"] is (not in_game)


def test_tdp_ownership_never_claims_a_menu_floor_without_one(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, PlainBackend)

    ownership = plugin._tdp_ownership_state(plugin._tdp_backend.observe())

    assert ownership["menu_floor"] is False
