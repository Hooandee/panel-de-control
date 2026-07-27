"""Read-only detection of PowerStation's TDP manager."""

import re
import time

from controllers.detect import _run

_UNIT = "powerstation.service"
_SERVICE = "org.shadowblip.PowerStation"
_TDP_INTERFACE = "org.shadowblip.GPU.Card.TDP"
_CARD_PATH = re.compile(r"/org/shadowblip/Performance/GPU/Card\d+$")


def _card_paths(tree: str) -> list[str]:
    paths = []
    for line in tree.splitlines():
        match = re.search(r"(/[^\s]+)", line)
        if match and _CARD_PATH.fullmatch(match.group(1)):
            paths.append(match.group(1))
    return paths


def probe(run=_run) -> bool:
    if run(["systemctl", "is-active", _UNIT]) != "active":
        return False
    tree = run(["busctl", "--system", "tree", _SERVICE])
    for path in _card_paths(tree):
        interface = run(
            ["busctl", "--system", "introspect", _SERVICE, path, _TDP_INTERFACE]
        )
        if interface:
            return True
    return False


class Detector:
    def __init__(self, run=_run, clock=time.monotonic, cache_seconds=15):
        self._run = run
        self._clock = clock
        self._cache_seconds = float(cache_seconds)
        self._checked_at = None
        self._active = False

    def tdp_active(self) -> bool:
        now = self._clock()
        if (
            self._checked_at is not None
            and now - self._checked_at < self._cache_seconds
        ):
            return self._active
        self._active = probe(self._run)
        self._checked_at = now
        return self._active
