from collections import deque
from dataclasses import asdict, dataclass

WINDOW_S = 10.0
SETTLE_S = 4.0
MIN_TOLERANCE_W = 2.0
RELATIVE_TOLERANCE = 0.15


@dataclass(frozen=True)
class MeasuredVerdict:
    state: str
    target_w: int | None
    average_w: float | None
    samples: int

    def as_dict(self) -> dict:
        return asdict(self)


def exceed_threshold_w(target_w: int) -> float:
    return target_w + max(MIN_TOLERANCE_W, target_w * RELATIVE_TOLERANCE)


class MeasuredLimitWatch:
    """Compares the APU package power against the last written PL1.

    Package power below the limit cannot prove the limit was applied (the load may
    simply be light), so the verdicts are `within_limit` and `exceeded`, never
    `applied`."""

    def __init__(self, window_s: float = WINDOW_S, settle_s: float = SETTLE_S):
        self._window_s = window_s
        self._settle_s = settle_s
        self._target_w = None
        self._since = None
        self._samples = deque()

    @property
    def target_w(self) -> int | None:
        return self._target_w

    def reset(self, target_w: int | None, now: float) -> None:
        self._target_w = int(target_w) if target_w is not None else None
        self._since = now
        self._samples.clear()

    def feed(self, watts: float | None, now: float) -> MeasuredVerdict:
        target = self._target_w
        if target is None or watts is None or self._since is None:
            return MeasuredVerdict("warming", target, None, len(self._samples))
        if now - self._since < self._settle_s:
            return MeasuredVerdict("warming", target, None, 0)
        self._samples.append((now, float(watts)))
        while self._samples and now - self._samples[0][0] > self._window_s:
            self._samples.popleft()
        span = now - self._samples[0][0]
        average = round(sum(w for _, w in self._samples) / len(self._samples), 1)
        if span < self._window_s * 0.8:
            return MeasuredVerdict("warming", target, average, len(self._samples))
        state = "exceeded" if average > exceed_threshold_w(target) else "within_limit"
        return MeasuredVerdict(state, target, average, len(self._samples))
