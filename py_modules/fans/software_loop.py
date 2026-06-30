"""Software-loop fan backends — for devices with NO hardware temp→pwm curve
table. We are the controller: read temp, interpolate the (canonical 0–255 pwm)
curve to a duty, map duty → an RPM target, write it, and re-assert periodically
(the EC reclaims the fan otherwise). Release = hand control back to firmware.

Members: Steam Deck (steamdeck_hwmon `fan1_target` RPM). Legion Go 2 (raw EC)
is a separate W4 backend with the same shape.

Canonical curve stays temp→pwm(0–255); each backend reinterprets pwm/255 as a
fraction of its RPM range so the F2/F3 curve representation is portable.
"""

import asyncio
import glob
import os
from typing import Callable, Optional

# Reuse the sysfs read/write + interp helpers from control (no 4th copy).
from fans.control import _interp, _read, _read_int, _write, sanitize_curve

_HWMON = "sys/class/hwmon"
_LOOP_INTERVAL = 1.5  # s — re-assert cadence (EC can reclaim the fan)


class SoftwareLoopBackend:
    """Base: owns the stored curve, the asyncio re-assert loop, and duty→RPM."""

    name = "software-loop"
    min_rpm = 0
    max_rpm = 7000
    # While a curve is ACTIVE the driven target must never be 0 — on these devices
    # writing 0 to the target/override is the "release to firmware" sentinel
    # (see _release). A 0%-duty cool point would otherwise silently hand the fan
    # back to the EC while read_state still reports manual. Clamp to >=1 so driving
    # stays manual (matches LeGo2's 0→1 behaviour); explicit release still writes 0.
    min_drive_rpm = 1

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None, root: str = "/") -> None:
        self._temp_fn = temp_fn
        self._root = root
        self._points: Optional[list] = None
        self._task: Optional[asyncio.Task] = None
        self._dir: Optional[str] = self._find_chip()

    # --- subclass hooks --------------------------------------------------------
    def _find_chip(self) -> Optional[str]:
        raise NotImplementedError

    def _write_target(self, rpm: int) -> bool:
        raise NotImplementedError

    def _release(self) -> bool:
        raise NotImplementedError

    def _read_rpm(self) -> Optional[int]:
        return None

    # --- common API ------------------------------------------------------------
    @property
    def supported(self) -> bool:
        return self._dir is not None

    def _duty_to_target(self, duty: int) -> int:
        frac = max(0, min(255, duty)) / 255
        return int(round(self.min_rpm + frac * (self.max_rpm - self.min_rpm)))

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        if self._points is None or temp is None:
            return None
        # Clamp to min_drive_rpm so an active curve never writes the release sentinel.
        return max(self.min_drive_rpm, self._duty_to_target(_interp(self._points, temp)))

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        rpm = self._read_rpm()
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if self._points else 2,
                          "rpm": rpm, "points": []}]}

    def apply_curve_all(self, points: list) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        self._points = [list(p) for p in sanitize_curve(points)]
        self._apply_once()   # immediate response, before the loop's first tick
        self.start()
        return {"ok": True, "detail": f"{self.name} curve applied (software loop)"}

    def set_curve(self, fan_key, points: list) -> dict:
        return self.apply_curve_all(points)

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        # Clear points FIRST so any in-flight loop tick computes target_for_temp→None
        # and writes nothing, then stop the loop and release. (A full fix awaits the
        # cancelled task — deferred async cancel+await, shared with the sampler.)
        self._points = None
        self.stop()
        ok = self._release()
        return {"ok": ok, "detail": "released to firmware" if ok else "release write failed"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)

    # --- the loop --------------------------------------------------------------
    def _apply_once(self) -> None:
        temp = self._temp_fn() if self._temp_fn else None
        target = self.target_for_temp(temp)
        if target is not None:
            self._write_target(target)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop (tests / import time) — no-op
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_LOOP_INTERVAL)
                self._apply_once()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — loop must never die
                pass


_DECK_CHIPS = ("steamdeck_hwmon", "jupiter")
_DECK_MAX_RPM = {"Jupiter": 7300, "Galileo": 7300}


class SteamDeckFanBackend(SoftwareLoopBackend):
    """Steam Deck (LCD/Galileo): write ``fan1_target`` (RPM); release = write 0.

    Std-BIOS retail units need no recalculate handoff — writing fan1_target
    overrides the EC, and 0 hands it back. We re-assert because the EC reclaims.
    """

    def __init__(self, temp_fn=None, root: str = "/") -> None:
        super().__init__(temp_fn=temp_fn, root=root)
        board = _read(os.path.join(root, "sys/class/dmi/id/board_name")) or ""
        self.max_rpm = _DECK_MAX_RPM.get(board, 7000)

    def _find_chip(self) -> Optional[str]:
        pattern = os.path.join(self._root, _HWMON, "hwmon*")
        for d in sorted(glob.glob(pattern)):
            if _read(os.path.join(d, "name")) in _DECK_CHIPS:
                if os.path.exists(os.path.join(d, "fan1_target")):
                    self.name = _read(os.path.join(d, "name"))
                    return d
        return None

    def _write_target(self, rpm: int) -> bool:
        return _write(os.path.join(self._dir, "fan1_target"), str(int(rpm)))

    def _release(self) -> bool:
        return _write(os.path.join(self._dir, "fan1_target"), "0")

    def _read_rpm(self) -> Optional[int]:
        return _read_int(os.path.join(self._dir, "fan1_input"))
