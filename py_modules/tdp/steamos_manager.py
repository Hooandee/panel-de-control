"""Read-only service presence; presence does not establish power ownership."""

import time

from journal_context import active_services


class Detector:
    def __init__(self, run, clock=time.monotonic, cache_seconds=15):
        self._run = run
        self._clock = clock
        self._cache_seconds = float(cache_seconds)
        self._checked_at = None
        self._active = None

    def _capture(self, command):
        output = self._run(command)
        if output is None or output.startswith('[exit '):
            raise OSError('service detection unavailable')
        return output

    def active(self) -> bool | None:
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < self._cache_seconds:
            return self._active
        try:
            self._active = 'steamos-manager' in active_services(self._capture)
        except Exception:
            self._active = None
        self._checked_at = now
        return self._active
