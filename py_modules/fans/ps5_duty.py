"""Read-only duty observation for the PS5 hwmon ABI (no tachometer)."""
import re
import threading
import time

from ps5.firmware_io import FirmwareIo

READ_REFRESH_S = 10.0


class Ps5FanDuty:
    def __init__(self, io=None, clock=time.monotonic):
        self._io = io if io is not None else FirmwareIo()
        self._clock = clock
        self._lock = threading.Lock()
        self._path = None
        self._read_at = None
        self._cached = None
        self._diagnostics = {}

    def read(self, path):
        # Concurrent RPC/telemetry calls must not queue another ICC read or wait
        # behind one already in flight. A refresh clears the previous observation.
        if not self._lock.acquire(blocking=False):
            return None
        try:
            now = self._clock()
            if path == self._path and self._read_at is not None and now - self._read_at < READ_REFRESH_S:
                return self._cached
            self._path = path
            self._read_at = now
            self._cached = None
            self._diagnostics = self._io.diagnostics()
            # hwmon can be renumbered while an old ICC request is still stuck.
            # Keep a single outstanding firmware read even across that rename.
            if self._diagnostics.get("stuck"):
                return None
            raw, error = self._io.read(path)
            self._diagnostics = self._io.diagnostics()
            if error is None and isinstance(raw, str) and re.fullmatch(r"[0-9]{1,3}", raw):
                pwm = int(raw)
                if 0 <= pwm <= 255:
                    self._cached = pwm
            return self._cached
        finally:
            self._lock.release()

    def diagnostics(self):
        return dict(self._diagnostics)
