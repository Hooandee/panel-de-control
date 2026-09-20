import errno
import glob
import os
import threading
import time


_ENGINES = ("rcs", "ccs")


class IntelGpuUtil:
    """Non-blocking Intel Xe utilisation from cumulative DRM client counters."""

    def __init__(self, root="/", cache_s=0.1):
        self._root = root
        self._cache_s = max(0.0, float(cache_s))
        self._previous = {}
        self._last_value = None
        self._last_read_at = None
        self._last_snapshot = {
            "scanned": 0,
            "unreadable": 0,
            "permission_denied": 0,
            "xe_fdinfo": 0,
            "clients": 0,
            "engines": 0,
        }
        self._last_diagnostics = {
            "source": "intel_xe_fdinfo",
            "state": "not_sampled",
        }
        self._lock = threading.Lock()

    def _snapshot(self):
        clients = {}
        pattern = os.path.join(self._root, "proc/[0-9]*/fdinfo/*")
        paths = glob.glob(pattern)
        stats = {
            "scanned": len(paths),
            "unreadable": 0,
            "permission_denied": 0,
            "xe_fdinfo": 0,
            "clients": 0,
            "engines": 0,
        }
        for path in paths:
            try:
                with open(path) as handle:
                    fields = {
                        key: value.strip()
                        for line in handle
                        if ":" in line
                        for key, value in (line.split(":", 1),)
                    }
            except OSError as error:
                stats["unreadable"] += 1
                if error.errno in (errno.EACCES, errno.EPERM):
                    stats["permission_denied"] += 1
                continue
            if fields.get("drm-driver") != "xe":
                continue
            stats["xe_fdinfo"] += 1
            device = fields.get("drm-pdev")
            client = fields.get("drm-client-id")
            if not device or not client:
                continue
            counters = clients.setdefault((device, client), {})
            for engine in _ENGINES:
                try:
                    current = (
                        int(fields[f"drm-cycles-{engine}"]),
                        int(fields[f"drm-total-cycles-{engine}"]),
                    )
                except (KeyError, ValueError):
                    continue
                previous = counters.get(engine)
                if previous is None or current[1] > previous[1]:
                    counters[engine] = current
        stats["clients"] = len(clients)
        stats["engines"] = sum(len(counters) for counters in clients.values())
        self._last_snapshot = stats
        return clients

    def _sample_state(self, has_value):
        stats = self._last_snapshot
        if has_value:
            return "ok"
        if stats["clients"]:
            return "warming"
        if stats["permission_denied"]:
            return "permission_denied"
        if stats["xe_fdinfo"]:
            return "incompatible_fdinfo"
        return "no_xe_clients"

    def read_gpu_busy(self):
        with self._lock:
            now = time.monotonic()
            if (
                self._last_read_at is not None
                and now - self._last_read_at < self._cache_s
            ):
                return self._last_value
            current = self._snapshot()
            previous = self._previous
            self._previous = current
            values = []
            for engine in _ENGINES:
                busy_delta = 0
                total_delta = 0
                for client, counters in current.items():
                    before = previous.get(client, {}).get(engine)
                    after = counters.get(engine)
                    if before is None or after is None:
                        continue
                    busy = after[0] - before[0]
                    total = after[1] - before[1]
                    if busy < 0 or total <= 0:
                        continue
                    busy_delta += busy
                    total_delta = max(total_delta, total)
                if total_delta > 0:
                    values.append(100.0 * busy_delta / total_delta)
            self._last_value = (
                round(max(0.0, min(100.0, max(values))))
                if values
                else None
            )
            self._last_read_at = time.monotonic()
            self._last_diagnostics = {
                "source": "intel_xe_fdinfo",
                "state": self._sample_state(bool(values)),
                **self._last_snapshot,
            }
            return self._last_value

    def diagnostics(self):
        with self._lock:
            return dict(self._last_diagnostics)
