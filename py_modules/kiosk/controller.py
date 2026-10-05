"""Kiosk lifecycle: detect the secondary display, serve its RPCs, keep the bottom screen alive."""

import asyncio
import time
from typing import Any, Awaitable, Callable, Iterable

from kiosk import displays
from kiosk.launcher import KioskLauncher
from kiosk.server import KioskServer

SUPERVISE_S = 10.0
RETRY_MIN_S = 5.0
RETRY_MAX_S = 60.0
# Reasons that mean this machine can never show the kiosk (vs. "not right now").
UNSUPPORTED_REASONS = frozenset({"no_mechanism", "no_secondary_display"})

Journal = Callable[..., None]


class KioskController:
    def __init__(
        self,
        dispatch: Callable[[str, list], Awaitable[Any]],
        allowed_methods: Iterable[str],
        journal: Journal,
        enabled: bool = False,
        detect: Callable[[], displays.Detection] = displays.detect,
        launcher_factory: Callable[[displays.SecondaryDisplay], KioskLauncher] = KioskLauncher,
        server_factory: Callable[..., KioskServer] = KioskServer,
        clock: Callable[[], float] = time.monotonic,
        art: Callable[[str, str], "tuple[str, str] | None"] = lambda _appid, _kind: None,
        brightness: float | None = None,
    ):
        self.enabled = enabled
        # The driver resets the panel to full brightness on every boot.
        self._brightness = brightness
        self._journal = journal
        self._detect = detect
        self._launcher_factory = launcher_factory
        self._clock = clock
        self._server = server_factory(
            dispatch, allowed_methods,
            on_error=lambda method, error: journal("WARNING", "rpc_failed", method=method, error=error),
            art=art,
        )
        self._detection = displays.Detection(None, "not_checked")
        self._launcher: KioskLauncher | None = None
        self._running = False
        self._retry_at = 0.0
        self._retry_delay = RETRY_MIN_S
        self._last_error: str | None = None
        self._screen_off = False
        self._lock = asyncio.Lock()

    def state(self) -> dict:
        reason = self._detection.reason
        return {
            "supported": reason not in UNSUPPORTED_REASONS,
            "available": self._detection.display is not None,
            "reason": reason,
            "enabled": self.enabled,
            "running": self._running,
            "mechanism": self._detection.display.mechanism if self._detection.display else None,
            "last_error": self._last_error,
            "screen_off": self._screen_off,
            "brightness": self._brightness,
        }

    def rpc_calls(self) -> dict[str, list[float]]:
        return {name: list(tally) for name, tally in self._server.calls.items()}

    def session(self):
        display = self._detection.display
        return display.session if display else None

    def secondary_connector(self) -> str | None:
        display = self._detection.display
        return display.connector if display else None

    async def set_enabled(self, enabled: bool) -> dict:
        self.enabled = bool(enabled)
        self._journal("INFO", "enabled" if self.enabled else "disabled")
        self._retry_at = 0.0
        self._retry_delay = RETRY_MIN_S
        await self.tick()
        return self.state()

    async def refresh(self) -> dict:
        async with self._lock:
            await self._redetect()
        return self.state()

    async def _redetect(self) -> displays.Detection:
        detection = await asyncio.to_thread(self._detect)
        if detection.reason != self._detection.reason:
            self._journal("INFO", "display", reason=detection.reason)
        self._detection = detection
        return detection

    async def tick(self) -> None:
        async with self._lock:
            detection = await self._redetect()
            if not self.enabled or detection.display is None:
                await self._stop()
                return
            if self._launcher is None or self._launcher.display != detection.display:
                await self._stop()
                self._launcher = self._launcher_factory(detection.display)
                # A unit left by a Panel that died points at that Panel's port and token.
                if await asyncio.to_thread(self._launcher.is_active):
                    await asyncio.to_thread(self._launcher.stop)
                    self._journal("INFO", "stale_unit_restarted")
            await self._ensure_running()

    async def _ensure_running(self) -> None:
        assert self._launcher is not None
        if self._server.port is None:
            await self._server.start()
        was_running = self._running
        self._running = await asyncio.to_thread(self._launcher.is_active)
        if was_running and not self._running:
            self._journal("WARNING", "exited", detail=await asyncio.to_thread(self._launcher.last_words))
        if self._running:
            self._retry_delay = RETRY_MIN_S
            return
        now = self._clock()
        if now < self._retry_at:
            return
        ok, detail = await asyncio.to_thread(self._launcher.start, self._server.url)
        self._retry_at = now + self._retry_delay
        self._retry_delay = min(self._retry_delay * 2, RETRY_MAX_S)
        self._running = ok
        if ok:
            self._last_error = None
            self._journal("INFO", "launched", mechanism=self._launcher.display.mechanism)
            if self._brightness is not None and self._launcher.display.backlight:
                await asyncio.to_thread(displays.set_backlight_level, self._launcher.display.backlight, self._brightness)
        else:
            self._last_error = detail or "start_failed"
            self._journal("WARNING", "launch_failed", detail=self._last_error)

    async def set_screen_off(self, off: bool) -> dict:
        display = self._detection.display
        if display is None or not display.backlight:
            return self.state()
        if await asyncio.to_thread(displays.set_backlight_power, display.backlight, not off):
            self._screen_off = bool(off)
            self._journal("INFO", "screen_off" if off else "screen_on")
        else:
            self._journal("WARNING", "backlight_failed", backlight=display.backlight)
        return self.state()

    async def brightness(self) -> float | None:
        display = self._detection.display
        if display is None or not display.backlight:
            return None
        return await asyncio.to_thread(displays.backlight_level, display.backlight)

    async def set_brightness(self, fraction: float) -> float | None:
        display = self._detection.display
        if display is None or not display.backlight:
            return None
        applied = await asyncio.to_thread(displays.set_backlight_level, display.backlight, fraction)
        if applied is None:
            self._journal("WARNING", "brightness_failed", backlight=display.backlight)
            return None
        self._brightness = applied
        return applied

    async def _stop(self) -> None:
        if self._screen_off and self._detection.display is not None:
            await asyncio.to_thread(displays.set_backlight_power, self._detection.display.backlight, True)
            self._screen_off = False
        if self._launcher is not None:
            launcher, self._launcher = self._launcher, None
            ok, detail = await asyncio.to_thread(launcher.stop)
            self._journal("INFO" if ok else "WARNING", "stopped", ok=ok, detail=detail or None)
        self._running = False
        await self._server.stop()

    async def supervise(self) -> None:
        while True:
            try:
                if self.enabled or self._launcher is not None:
                    await self.tick()
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._journal("ERROR", "supervise_failed", error=self._last_error)
            await asyncio.sleep(SUPERVISE_S)

    async def shutdown(self) -> None:
        async with self._lock:
            await self._stop()
