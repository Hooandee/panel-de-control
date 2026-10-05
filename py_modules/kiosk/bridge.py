"""Ask the Panel instance running inside Steam to do what only Steam's client can do."""

import asyncio
import itertools
from typing import Any, Awaitable, Callable

EVENT = "pdc_kiosk_steam"
TIMEOUT_S = 4.0
MAX_PENDING = 16

# Mirrors the handler table in src/kiosk/steamBridge.ts; anything else is refused here.
ACTIONS = frozenset({
    "brightness.get", "brightness.set",
    "volume.get", "volume.set",
    "refresh.get", "refresh.set",
    "screenshot", "keyboard", "quick_access",
    "colores.state", "colores.call", "colores.install",
    "perf.view", "perf.preset", "perf.level", "perf.target",
    "snapshot",
})

# Polled by the bottom screen; they change nothing, so they stay out of the journal.
READS = frozenset({"brightness.get", "volume.get", "refresh.get", "perf.view", "colores.state", "snapshot"})

Emit = Callable[..., Awaitable[Any]]


class BridgeError(Exception):
    pass


class SteamBridge:
    def __init__(self, emit: Emit, timeout_s: float = TIMEOUT_S):
        self._emit = emit
        self._timeout_s = timeout_s
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}

    async def call(self, action: str, args: list) -> Any:
        if action not in ACTIONS:
            raise BridgeError("unknown_action")
        if len(self._pending) >= MAX_PENDING:
            raise BridgeError("busy")
        request_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._emit(EVENT, request_id, action, list(args))
            return await asyncio.wait_for(future, self._timeout_s)
        except asyncio.TimeoutError as error:
            raise BridgeError("steam_unavailable") from error
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, request_id: int, ok: bool, result: Any) -> bool:
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        if ok:
            future.set_result(result)
        else:
            future.set_exception(BridgeError(str(result or "steam_failed")))
        return True
