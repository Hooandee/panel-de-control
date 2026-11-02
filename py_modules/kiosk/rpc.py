"""Kiosk RPC surface: the plugin methods the bottom screen calls, and nothing else."""

import inspect
from typing import Any, Awaitable, Callable


# The kiosk's token travels in its URL and any process of the same account can read it, so the
# channel offers only what the bottom screen calls; developer and remote-access methods stay
# reachable from Decky alone.
KIOSK_RPC_METHODS = frozenset({
    "get_battery_state",
    "get_cpu_state",
    "get_fan_curve_state",
    "get_kiosk_brightness",
    "get_kiosk_game",
    "get_kiosk_live",
    "get_kiosk_session",
    "get_kiosk_vitals",
    "get_ui_prefs",
    "kiosk_steam",
    "set_cpu_boost",
    "set_fan_auto",
    "set_fan_preset",
    "set_kiosk_brightness",
    "set_kiosk_screen_off",
})


def kiosk_rpc_methods(plugin: object) -> frozenset[str]:
    return frozenset(
        name
        for name in KIOSK_RPC_METHODS
        if inspect.iscoroutinefunction(getattr(type(plugin), name, None))
    )


def plugin_dispatch(plugin: object) -> Callable[[str, list], Awaitable[Any]]:
    async def dispatch(name: str, args: list) -> Any:
        return await getattr(plugin, name)(*args)

    return dispatch
