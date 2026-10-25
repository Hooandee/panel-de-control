"""Write budget for the panel: every GIF the panel accepts is stored in its flash."""

import time
from collections.abc import Callable
from enum import Enum

_HOUR = 3600.0
_DAY = 24 * _HOUR
_MIN_GAP = {"scheduled": 20.0, "live": 60.0, "alert": 0.0}
_AUTOMATIC_PER_HOUR = 60
_AUTOMATIC_PER_DAY = 600
_USER_PER_HOUR = 240
_BOUNDARY_GAP = 60.0
_BOUNDARY_PER_HOUR = 30
DAILY_CEILING = 1500


class Decision(Enum):
    ALLOW = "allow"
    DUPLICATE = "duplicate"
    TOO_SOON = "too_soon"
    BUDGET = "budget"


class Governor:
    def __init__(self, clock: Callable[[], float] = time.time, snapshot: dict | None = None):
        self._clock = clock
        self._uploads: list[tuple[float, str, str | None]] = []
        self._last_hash: str | None = None
        self._restore(snapshot or {})

    def decide(self, content_hash: str, kind: str, metric: str | None = None) -> Decision:
        if content_hash == self._last_hash:
            return Decision.DUPLICATE
        now = self._clock()
        self._prune(now)
        if len(self._uploads) >= DAILY_CEILING:
            return Decision.BUDGET
        if kind == "user":
            recent = sum(1 for t, k, _ in self._uploads if k == "user" and now - t < _HOUR)
            return Decision.BUDGET if recent >= _USER_PER_HOUR else Decision.ALLOW
        if kind == "boundary":
            # A precomputed window runs out: without this upload a clock would loop back. It skips the
            # automatic budget but keeps its own, so a scene with a wrong expiry cannot hammer the flash.
            boundaries = [t for t, k, _ in self._uploads if k == "boundary" and now - t < _HOUR]
            if len(boundaries) >= _BOUNDARY_PER_HOUR:
                return Decision.BUDGET
            if boundaries and now - max(boundaries) < _BOUNDARY_GAP:
                return Decision.TOO_SOON
            return Decision.ALLOW
        automatic = [(t, k, m) for t, k, m in self._uploads if k not in ("user", "boundary")]
        if sum(1 for t, _, _ in automatic if now - t < _HOUR) >= _AUTOMATIC_PER_HOUR:
            return Decision.BUDGET
        if len(automatic) >= _AUTOMATIC_PER_DAY:
            return Decision.BUDGET
        gap = _MIN_GAP.get(kind, _MIN_GAP["scheduled"])
        if kind == "live":
            relevant = [t for t, _, m in self._uploads if m == metric]
        else:
            relevant = [t for t, _, _ in automatic]
        if relevant and now - max(relevant) < gap:
            return Decision.TOO_SOON
        return Decision.ALLOW

    def retry_in(self, kind: str, metric: str | None = None, decision: "Decision | None" = None) -> float:
        now = self._clock()
        automatic = [(t, k, m) for t, k, m in self._uploads if k not in ("user", "boundary")]
        gap = _MIN_GAP.get(kind, _MIN_GAP["scheduled"])
        if kind == "live":
            relevant = [t for t, _, m in self._uploads if m == metric]
        elif kind == "boundary":
            gap, relevant = _BOUNDARY_GAP, [t for t, k, _ in self._uploads if k == "boundary"]
        else:
            relevant = [t for t, _, _ in automatic]
        wait = gap - (now - max(relevant)) if relevant else 0.0
        if decision is Decision.BUDGET or sum(1 for t, _, _ in automatic if now - t < _HOUR) >= _AUTOMATIC_PER_HOUR:
            wait = max(wait, 60.0)
        return max(1.0, wait)

    def record(self, content_hash: str, ok: bool, kind: str = "user", metric: str | None = None) -> None:
        if not ok:
            return
        self._uploads.append((self._clock(), kind, metric))
        self._last_hash = content_hash

    def forget_shown(self) -> None:
        self._last_hash = None

    def stats(self) -> dict:
        now = self._clock()
        self._prune(now)
        return {
            "last_hour": sum(1 for t, _, _ in self._uploads if now - t < _HOUR),
            "last_day": len(self._uploads),
        }

    def snapshot(self) -> dict:
        return {"last_hash": self._last_hash, "uploads": [list(u) for u in self._uploads]}

    def _prune(self, now: float) -> None:
        self._uploads = [u for u in self._uploads if now - u[0] < _DAY]

    def _restore(self, snapshot: dict) -> None:
        last = snapshot.get("last_hash")
        self._last_hash = last if isinstance(last, str) else None
        uploads = snapshot.get("uploads")
        if not isinstance(uploads, list):
            return
        for item in uploads:
            if (isinstance(item, list) and len(item) == 3 and isinstance(item[0], (int, float))
                    and isinstance(item[1], str) and (item[2] is None or isinstance(item[2], str))):
                self._uploads.append((float(item[0]), item[1], item[2]))
