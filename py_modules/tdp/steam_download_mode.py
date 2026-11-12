"""Steam's download mode on the Steam Deck.

With a download running and the screen turned off from the power button, Steam asks
steamos-manager (LowPowerMode1.EnterDownloadMode) to lower the TDP to the device's
`download_mode_limit`, stop jupiter-fan-control and pin the fan at a low speed. Pushing
our own TDP back in that state runs the APU hot with the fan held low. When Steam leaves
the mode, steamos-manager restores the limit it cached on entry.
"""
from __future__ import annotations

import os
import subprocess
import tomllib
from typing import Callable

from tdp.types import TdpObservation
from user_session import UserSession, spawn_args

DECK_CONFIG = "usr/share/steamos-manager/devices/steam-deck.toml"
_MANAGER = ("com.steampowered.SteamOSManager1", "/com/steampowered/SteamOSManager1")
_LOW_POWER = "com.steampowered.SteamOSManager1.LowPowerMode1"
# steamos-manager writes the limit a moment before it stops jupiter-fan-control.
PENDING_S = 5.0
RECHECK_S = 10.0


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


def download_mode_handles(session: UserSession | None, run=subprocess.run) -> int | None:
    """Open download mode handles in steamos-manager; None when it cannot be asked."""
    if session is None:
        return None
    command, env, identity = spawn_args(
        session, ["busctl", "--user", "call", *_MANAGER, _LOW_POWER, "ListDownloadModeHandles"],
    )
    try:
        result = run(command, env=env, capture_output=True, text=True, timeout=3, check=False, **identity)
    except (OSError, subprocess.SubprocessError):
        return None
    parts = result.stdout.split() if result.returncode == 0 else []
    if len(parts) >= 2 and parts[0].startswith("a") and parts[1].isdigit():
        return int(parts[1])
    return None


class SteamDownloadModeHold:
    def __init__(self, limit_w: int | None):
        self.limit_w = limit_w
        self.active = False
        self.holding = False
        self._entered_at: float | None = None
        self._pending_since: float | None = None
        self._checked_at = float("-inf")
        self._unconfirmed_reported = False
        self._last: dict | None = None
        self._count = 0

    def _at_limit(self, observation: TdpObservation) -> bool | None:
        if not observation.readable:
            return None
        values = list(observation.applied_values().values())
        if not values:
            return None
        return all(value == self.limit_w for value in values)

    def _candidate(self, observation, target: dict, last_written: dict | None) -> bool:
        """Rails sit at the download limit, which neither we nor our target put there."""
        if not self._at_limit(observation):
            return False
        if all(watts == self.limit_w for watts in target.values()):
            return False
        return not (
            last_written
            and all(watts == self.limit_w for watts in last_written.values())
        )

    def step(
        self,
        observation: TdpObservation,
        target: dict,
        last_written: dict | None,
        now: float,
        steam_signal: Callable[[], bool | None],
    ) -> str | None:
        """Advance one guard tick; returns 'entered', 'left' or 'unconfirmed' on a
        transition. `holding` tells the guard to write nothing this tick."""
        if self.limit_w is None:
            self.holding = False
            return None
        if self.active:
            transition = None
            if self._at_limit(observation) is False:
                transition = self._leave(now, "rails_changed")
            elif now - self._checked_at >= RECHECK_S:
                self._checked_at = now
                if steam_signal() is False:
                    transition = self._leave(now, "steam_left")
            self.holding = self.active
            return transition
        if not self._candidate(observation, target, last_written):
            self._pending_since = None
            self._unconfirmed_reported = False
            self.holding = False
            return None
        if steam_signal():
            self.active = self.holding = True
            self._entered_at = self._checked_at = now
            self._pending_since = None
            self._count += 1
            return "entered"
        if self._pending_since is None:
            self._pending_since = now
        self.holding = now - self._pending_since < PENDING_S
        if self.holding or self._unconfirmed_reported:
            return None
        self._unconfirmed_reported = True
        return "unconfirmed"

    def release(self, now: float) -> bool:
        if not self.active:
            return False
        self._leave(now, "user")
        return True

    def _leave(self, now: float, why: str) -> str:
        entered = self._entered_at if self._entered_at is not None else now
        self._last = {
            "entered_at": entered,
            "left_at": now,
            "held_s": round(now - entered, 1),
            "why": why,
        }
        self.active = self.holding = False
        self._entered_at = None
        return "left"

    def diagnostics(self) -> dict:
        return {
            "limit_w": self.limit_w,
            "active": self.active,
            "pending_since": self._pending_since,
            "entered_at": self._entered_at,
            "count": self._count,
            "last": self._last,
        }
