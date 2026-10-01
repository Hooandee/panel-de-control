"""GPU utilisation from DRM client statistics (``/proc/<pid>/fdinfo``), the
standard source for GPUs without a busy-percent node (Adreno/msm, Mali/panfrost,
panthor). Each call returns the busy share since the previous call, so the
window is the caller's own cadence and no sampling sleep is needed."""

import glob
import os
import time

_DRIVERS = frozenset({"msm", "panfrost", "panthor", "lima"})


def _clients(root: str) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = {}
    for path in glob.glob(os.path.join(root, "proc", "[0-9]*", "fdinfo", "*")):
        try:
            with open(path) as handle:
                text = handle.read()
        except OSError:
            continue
        if "drm-driver:" not in text:
            continue
        driver = client = None
        busy = 0
        for line in text.splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if key == "drm-driver":
                driver = value
            elif key == "drm-client-id":
                client = value
            elif key.startswith("drm-engine-") and value.endswith(" ns"):
                try:
                    busy += int(value[:-3])
                except ValueError:
                    pass
        if driver in _DRIVERS and client is not None:
            totals[(driver, client)] = max(totals.get((driver, client), 0), busy)
    return totals


class DrmFdinfoGpuBusy:
    def __init__(self, root: str = "/", clock=time.monotonic) -> None:
        self._root = root
        self._clock = clock
        self._last: tuple[float, dict] | None = None

    def read(self) -> int | None:
        now = self._clock()
        clients = _clients(self._root)
        previous, self._last = self._last, (now, clients)
        if previous is None or not clients:
            return None
        elapsed_ns = (now - previous[0]) * 1e9
        if elapsed_ns <= 0:
            return None
        busy = sum(
            max(0, total - previous[1][key])
            for key, total in clients.items()
            if key in previous[1]
        )
        return max(0, min(100, round(100 * busy / elapsed_ns)))
