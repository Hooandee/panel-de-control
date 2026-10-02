import asyncio
import sys

from kiosk.displays import Detection
from kiosk.rpc import public_rpc_methods
from test_tdp_guard_rpc import plugin  # noqa: F401


def _no_display(plugin):  # noqa: F811
    plugin._kiosk._detect = lambda: Detection(None, "no_mechanism")


def test_kiosk_setting_survives_a_restart(plugin):  # noqa: F811
    _no_display(plugin)
    state = asyncio.run(plugin.set_kiosk_enabled(True))
    assert state["enabled"] is True and state["supported"] is False
    main = sys.modules["main"]
    reloaded = main.Plugin()
    reloaded._init()
    assert reloaded._settings["kiosk_enabled"] is True
    assert reloaded._kiosk.enabled is True


def test_kiosk_state_is_reported_without_side_effects(plugin):  # noqa: F811
    _no_display(plugin)
    state = asyncio.run(plugin.get_kiosk_state())
    assert state == {
        "supported": False,
        "available": False,
        "reason": "no_mechanism",
        "enabled": False,
        "running": False,
        "mechanism": None,
        "last_error": None,
    }


def test_support_log_records_the_kiosk_setting(plugin):  # noqa: F811
    _no_display(plugin)
    asyncio.run(plugin.set_kiosk_enabled(True))
    assert plugin._support_settings_state()["kiosk_enabled"] is True


def test_kiosk_rpcs_match_what_decky_exposes(plugin):  # noqa: F811
    methods = public_rpc_methods(plugin)
    assert {"get_kiosk_state", "set_kiosk_enabled", "get_tdp_state", "get_ui_prefs"} <= methods
    assert not any(name.startswith("_") for name in methods)


def test_kiosk_game_name_comes_from_the_steam_library(plugin, tmp_path, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(main.kiosk_steam_game, "game_name", lambda home, appid: "Stardew Valley" if appid == "413150" else None)
    assert asyncio.run(plugin.get_kiosk_game("413150")) == {"appid": "413150", "name": "Stardew Valley"}
    assert asyncio.run(plugin.get_kiosk_game("1")) == {"appid": "1", "name": None}
