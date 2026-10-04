"""Single-finger touch from the secondary panel's evdev node, in panel pixels."""

import fcntl
import os
import struct
from dataclasses import dataclass

_EVENT = struct.Struct("llHHi")
_EV_SYN, _EV_KEY, _EV_ABS = 0, 1, 3
_SYN_REPORT = 0
_BTN_TOUCH = 0x14A
_ABS_X, _ABS_Y = 0x00, 0x01
_ABS_MT_SLOT, _ABS_MT_X, _ABS_MT_Y, _ABS_MT_TRACKING_ID = 0x2F, 0x35, 0x36, 0x39
_EVIOCGABS = 0x80184540


@dataclass(frozen=True)
class TouchEvent:
    kind: str  # "down" | "move" | "up"
    x: float
    y: float


def find_device(name: str, root: str = "/sys/class/input") -> str | None:
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    for entry in entries:
        if not entry.startswith("event"):
            continue
        try:
            with open(os.path.join(root, entry, "device", "name")) as handle:
                if handle.read().strip() == name:
                    return f"/dev/input/{entry}"
        except OSError:
            continue
    return None


class Touchscreen:
    def __init__(self, path: str, width: int, height: int):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self._scale_x = width / max(1, self._axis_max(_ABS_MT_X, _ABS_X) + 1)
        self._scale_y = height / max(1, self._axis_max(_ABS_MT_Y, _ABS_Y) + 1)
        self._x = self._y = 0.0
        self._down = False
        self._was_down = False
        self._moved = False
        self._slot = 0

    def _axis_max(self, *codes: int) -> int:
        for code in codes:
            info = bytearray(24)
            try:
                fcntl.ioctl(self.fd, _EVIOCGABS + code, info)
            except OSError:
                continue
            maximum = struct.unpack_from("iiiiii", info)[2]
            if maximum > 0:
                return maximum
        return 0

    def read(self) -> list[TouchEvent]:
        events: list[TouchEvent] = []
        while True:
            try:
                chunk = os.read(self.fd, _EVENT.size * 64)
            except BlockingIOError:
                return events
            if not chunk:
                return events
            for offset in range(0, len(chunk) - _EVENT.size + 1, _EVENT.size):
                _, _, kind, code, value = _EVENT.unpack_from(chunk, offset)
                self._feed(kind, code, value, events)

    def _feed(self, kind: int, code: int, value: int, events: list[TouchEvent]) -> None:
        if kind == _EV_ABS:
            if code == _ABS_MT_SLOT:
                self._slot = value
            elif self._slot != 0:
                return
            elif code in (_ABS_MT_X, _ABS_X):
                self._x, self._moved = value * self._scale_x, True
            elif code in (_ABS_MT_Y, _ABS_Y):
                self._y, self._moved = value * self._scale_y, True
            elif code == _ABS_MT_TRACKING_ID:
                self._down = value >= 0
        elif kind == _EV_KEY and code == _BTN_TOUCH:
            self._down = value != 0
        elif kind == _EV_SYN and code == _SYN_REPORT:
            if self._down and not self._was_down:
                events.append(TouchEvent("down", self._x, self._y))
            elif self._down and self._moved:
                events.append(TouchEvent("move", self._x, self._y))
            elif not self._down and self._was_down:
                events.append(TouchEvent("up", self._x, self._y))
            self._was_down = self._down
            self._moved = False

    def close(self) -> None:
        os.close(self.fd)
