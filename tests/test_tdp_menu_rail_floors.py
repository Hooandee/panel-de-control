import asyncio
import importlib
import sys
import types

import pytest

from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


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
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    import tdp.factory as factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: backend_cls())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": False)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": False, raising=False)
    plugin = main.Plugin()
    plugin._init()
    plugin._tdp_profiles.set_pl1("global", 5)
    return plugin


def _minimums(command):
    return {rail: command.safe_bounds[rail]["min"] for rail in ("pl1", "pl2", "pl3")}


def test_game_in_focus_keeps_the_requested_low_boost_rails(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    plugin._set_current_appid("42")

    command = plugin._capture_tdp_command("manual-watts", on_ac=False)

    assert _minimums(command) == {"pl1": 5, "pl2": 5, "pl3": 5}


def test_steam_home_without_a_game_keeps_the_menu_rail_floors(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)

    command = plugin._capture_tdp_command("lifecycle", on_ac=False)

    assert _minimums(command) == {"pl1": 5, "pl2": 15, "pl3": 20}


def test_open_menu_over_a_game_restores_the_menu_rail_floors(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    plugin._set_current_appid("42")
    plugin._ui_active = True

    command = plugin._capture_tdp_command("menu-floor", on_ac=False)

    assert _minimums(command) == {"pl1": 5, "pl2": 15, "pl3": 20}


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


def test_backends_without_menu_floors_are_unchanged_in_menus(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, PlainBackend)

    command = plugin._capture_tdp_command("lifecycle", on_ac=False)

    assert _minimums(command) == {"pl1": 5, "pl2": 5, "pl3": 5}


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


def test_menu_toggle_without_menu_floors_does_not_touch_power(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, PlainBackend)
    plugin._set_current_appid("42")
    reasons = []
    monkeypatch.setattr(
        plugin,
        "_schedule_tdp_apply",
        lambda reason, on_ac=None: reasons.append(reason),
    )

    asyncio.run(plugin.set_ui_active(True))
    asyncio.run(plugin.set_ui_active(False))

    assert reasons == []


@pytest.mark.parametrize("in_game", [False, True])
def test_menu_floor_state_is_reported_in_tdp_diagnostics(tmp_path, monkeypatch, in_game):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    if in_game:
        plugin._set_current_appid("42")

    assert plugin._tdp_diagnostics()["menu_rail_floors"] == {
        "floors": {"pl2": 15, "pl3": 20},
        "active": not in_game,
    }


def test_menu_floor_apply_survives_a_loaded_but_idle_auto_controller(tmp_path, monkeypatch):
    plugin = _plugin(tmp_path, monkeypatch, MenuFloorBackend)
    plugin._set_current_appid("42")
    plugin._auto_controller = object()
    monkeypatch.setattr(plugin, "_auto_runtime_active", lambda: False)

    async def no_auto_floor():
        return None

    monkeypatch.setattr(plugin, "_apply_auto_ui_floor", no_auto_floor)
    generations = []
    monkeypatch.setattr(
        plugin,
        "_schedule_tdp_apply",
        lambda reason, on_ac=None: generations.append(plugin._tdp_generation),
    )

    asyncio.run(plugin.set_ui_active(True))

    assert generations == [plugin._tdp_generation]


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
