import asyncio
import sys
import types

import pytest

if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER_HOME = "/tmp"
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                         warning=lambda *a, **k: None,
                                         error=lambda *a, **k: None)
    sys.modules["decky"] = decky

import main


def _plugin(shutting_down, error):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._shutting_down = shutting_down

    async def startup():
        raise error

    plugin._startup = startup
    return plugin


def test_a_shutdown_during_startup_stops_without_a_traceback():
    asyncio.run(_plugin(True, RuntimeError("plugin_shutting_down"))._main())


def test_real_startup_errors_still_surface():
    with pytest.raises(RuntimeError):
        asyncio.run(_plugin(False, RuntimeError("plugin_shutting_down"))._main())
    with pytest.raises(RuntimeError):
        asyncio.run(_plugin(True, RuntimeError("boom"))._main())
