"""Kiosk RPC surface: exactly the public coroutine methods Decky already lets the QAM call."""

import inspect
from typing import Any, Awaitable, Callable


def public_rpc_methods(plugin: object) -> frozenset[str]:
    return frozenset(
        name
        for name, member in inspect.getmembers(type(plugin))
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    )


def plugin_dispatch(plugin: object) -> Callable[[str, list], Awaitable[Any]]:
    async def dispatch(name: str, args: list) -> Any:
        return await getattr(plugin, name)(*args)

    return dispatch
