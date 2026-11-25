"""Bounded sysfs I/O for PS5 nodes served by the ICC link to the southbridge firmware.

A read or write of these nodes is a firmware round trip: it fails with ENODEV while
the link is not up yet (early boot) and can stall. Each call runs in its own daemon
thread with a deadline so a stalled link never holds Panel's shared executor. A node
whose call timed out is left alone for a cool-down, and while that stuck thread is
still in the kernel no second one is started for it. Nodes are tracked separately, so
a stalled light never blocks the fan."""
import threading
import time

TIMEOUT_S = 3.0
COOLDOWN_S = 30.0


class FirmwareIo:
    def __init__(self, timeout_s: float = TIMEOUT_S, cooldown_s: float = COOLDOWN_S,
                 clock=time.monotonic) -> None:
        self._timeout_s = timeout_s
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._blocked_until: dict[str, float] = {}
        self._stuck: dict[str, threading.Thread] = {}
        self.timeouts = 0
        self.last_error: dict | None = None

    def _call(self, op: str, path: str, fn):
        stuck = self._stuck.get(path)
        if stuck is not None:
            if stuck.is_alive():
                return None, "busy"
            del self._stuck[path]
        if self._clock() < self._blocked_until.get(path, 0.0):
            return None, "cooldown"
        outcome: dict = {}

        def run():
            try:
                outcome["value"] = fn()
            except OSError as error:
                outcome["errno"] = error.errno

        worker = threading.Thread(target=run, name="pdc-ps5-io", daemon=True)
        worker.start()
        worker.join(self._timeout_s)
        if worker.is_alive():
            self.timeouts += 1
            self._stuck[path] = worker
            self._blocked_until[path] = self._clock() + self._cooldown_s
            return self._fail(op, path, "timeout")
        if "errno" in outcome:
            return self._fail(op, path, f"errno_{outcome['errno']}")
        return outcome.get("value"), None

    def _fail(self, op: str, path: str, error: str):
        self.last_error = {"op": op, "path": path, "error": error}
        return None, error

    def read(self, path: str):
        def fn():
            with open(path) as handle:
                return handle.read().strip()
        return self._call("read", path, fn)

    def write(self, path: str, value) -> str | None:
        def fn():
            with open(path, "w") as handle:
                handle.write(f"{value}\n")
        return self._call("write", path, fn)[1]

    def diagnostics(self) -> dict:
        now = self._clock()
        return {
            "timeouts": self.timeouts,
            "last_error": self.last_error,
            "cooling_down": sorted(path for path, until in self._blocked_until.items() if now < until),
            "stuck": sorted(path for path, worker in self._stuck.items() if worker.is_alive()),
        }
