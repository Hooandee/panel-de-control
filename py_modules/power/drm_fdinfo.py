"""GPU utilisation from DRM client statistics (``/proc/<pid>/fdinfo``), the
standard source for GPUs without a busy-percent node (Adreno/msm, Mali/panfrost,
panthor). Each call returns the busy share since the previous call, so the
window is the caller's own cadence and no sampling sleep is needed."""

import glob
import os
import time

_DRIVERS = frozenset({"msm", "panfrost", "panthor", "lima"})


def _parse(path: str):
    try:
        with open(path) as handle:
            text = handle.read()
    except OSError:
        return None
    if "drm-driver:" not in text:
        return None
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
    if driver not in _DRIVERS or client is None:
        return None
    return (driver, client), busy


def _clients(root: str, paths=None) -> tuple[dict[tuple[str, str], int], list[str]]:
    totals: dict[tuple[str, str], int] = {}
    found = []
    if paths is None:
        paths = glob.glob(os.path.join(root, "proc", "[0-9]*", "fdinfo", "*"))
    for path in paths:
        parsed = _parse(path)
        if parsed is None:
            continue
        key, busy = parsed
        found.append(path)
        totals[key] = max(totals.get(key, 0), busy)
    return totals, found


# msm updates a client's busy time when a job completes, so a window much shorter
# than a frame swings between 0 and 100; several callers share one reader.
_MIN_WINDOW_S = 1.0
# A full /proc scan costs ~150 ms under x86 emulation; between scans only the
# descriptors already known to belong to a GPU client are re-read.
_RESCAN_S = 10.0


class DrmFdinfoGpuBusy:
    def __init__(self, root: str = "/", clock=time.monotonic) -> None:
        self._root = root
        self._clock = clock
        self._last: tuple[float, dict] | None = None
        self._value: int | None = None
        self._paths: list[str] = []
        self._scanned_at = float("-inf")
        self.has_clients = False

    def read(self) -> int | None:
        now = self._clock()
        if self._last is not None and now - self._last[0] < _MIN_WINDOW_S:
            return self._value
        if now - self._scanned_at >= _RESCAN_S:
            clients, self._paths = _clients(self._root)
            self._scanned_at = now
        else:
            clients, self._paths = _clients(self._root, self._paths)
        self.has_clients = bool(clients)
        previous, self._last = self._last, (now, clients)
        if previous is None or not clients:
            self._value = None
            return None
        elapsed_ns = (now - previous[0]) * 1e9
        busy = sum(
            max(0, total - previous[1][key])
            for key, total in clients.items()
            if key in previous[1]
        )
        self._value = max(0, min(100, round(100 * busy / elapsed_ns)))
        return self._value
