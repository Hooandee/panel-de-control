"""Steam's download mode on the Steam Deck.

With a download running and the screen turned off from the power button, Steam asks
steamos-manager (LowPowerMode1.EnterDownloadMode) to lower the TDP to the device's
`download_mode_limit`, stop jupiter-fan-control and pin the fan at a low speed. Pushing
our own TDP back in that state runs the APU hot with the fan held low. When Steam leaves
the mode, steamos-manager restores the limit it cached on entry.
"""
from __future__ import annotations

import os
import tomllib

from tdp.types import TdpObservation

DECK_CONFIG = "usr/share/steamos-manager/devices/steam-deck.toml"


def read_download_mode_limit(root: str = "/") -> int | None:
    try:
        with open(os.path.join(root, DECK_CONFIG), "rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    tdp_limit = config.get("tdp_limit")
    value = tdp_limit.get("download_mode_limit") if isinstance(tdp_limit, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


class SteamDownloadModeHold:
    def __init__(self, limit_w: int | None):
        self.limit_w = limit_w
        self.active = False
        self._entered_at: float | None = None
        self._last: dict | None = None
        self._count = 0

    def _at_limit(self, observation: TdpObservation) -> bool | None:
        if not observation.readable:
            return None
        values = list(observation.applied_values().values())
        if not values:
            return None
        return all(value == self.limit_w for value in values)

    def candidate(
        self, observation: TdpObservation, target: dict, last_written: dict | None,
    ) -> bool:
        """Rails sit at the download limit, which neither we nor our target put there."""
        if self.limit_w is None or self.active:
            return False
        if not self._at_limit(observation):
            return False
        if all(watts == self.limit_w for watts in target.values()):
            return False
        return not (
            last_written
            and all(watts == self.limit_w for watts in last_written.values())
        )

    def enter(self, now: float) -> None:
        self.active = True
        self._entered_at = now
        self._count += 1

    def observe(self, observation: TdpObservation, now: float) -> bool:
        """True when an active hold ends because the rails left the limit."""
        if self.active and self._at_limit(observation) is False:
            self._leave(now)
            return True
        return False

    def release(self, now: float) -> bool:
        if not self.active:
            return False
        self._leave(now)
        return True

    def _leave(self, now: float) -> None:
        entered = self._entered_at if self._entered_at is not None else now
        self._last = {
            "entered_at": entered,
            "left_at": now,
            "held_s": round(now - entered, 1),
        }
        self.active = False
        self._entered_at = None

    def diagnostics(self) -> dict:
        return {
            "limit_w": self.limit_w,
            "active": self.active,
            "entered_at": self._entered_at,
            "count": self._count,
            "last": self._last,
        }
