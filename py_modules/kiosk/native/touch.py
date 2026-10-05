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
    kind: str
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


class TouchParser:
    def __init__(self, scale_x: float = 1.0, scale_y: float = 1.0, x: int = 0, y: int = 0):
        self.scale_x, self.scale_y = scale_x, scale_y
        # The input core drops a position equal to the last one: a tap where the previous one lifted
        # carries no coordinates, so start from where the device says the finger was.
        self._x, self._y = x * scale_x, y * scale_y
        self._down = False
        self._was_down = False
        self._moved = False
        self._slot = 0
        self._partial = b""

    def feed(self, chunk: bytes) -> list[TouchEvent]:
        data = self._partial + chunk
        whole = len(data) - len(data) % _EVENT.size
        self._partial = data[whole:]
        events: list[TouchEvent] = []
        for offset in range(0, whole, _EVENT.size):
            _, _, kind, code, value = _EVENT.unpack_from(data, offset)
            self._event(kind, code, value, events)
        return events

    def _event(self, kind: int, code: int, value: int, events: list[TouchEvent]) -> None:
        if kind == _EV_ABS:
            if code == _ABS_MT_SLOT:
                self._slot = value
            elif self._slot != 0:
                return
            elif code in (_ABS_MT_X, _ABS_X):
                self._x, self._moved = value * self.scale_x, True
            elif code in (_ABS_MT_Y, _ABS_Y):
                self._y, self._moved = value * self.scale_y, True
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


class Touchscreen:
    def __init__(self, path: str, width: int, height: int):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        # ABS_X/ABS_Y keep the last position; the multitouch axes read 0 between touches.
        x_now, x_max = self._axis(_ABS_X, _ABS_MT_X)
        y_now, y_max = self._axis(_ABS_Y, _ABS_MT_Y)
        self.parser = TouchParser(width / max(1, x_max + 1), height / max(1, y_max + 1), x_now, y_now)

    def _axis(self, *codes: int) -> tuple[int, int]:
        for code in codes:
            info = bytearray(24)
            try:
                fcntl.ioctl(self.fd, _EVIOCGABS + code, info)
            except OSError:
                continue
            value, _, maximum = struct.unpack_from("iii", info)
            if maximum > 0:
                return value, maximum
        return 0, 0

    def read(self) -> list[TouchEvent]:
        events: list[TouchEvent] = []
        while True:
            try:
                chunk = os.read(self.fd, _EVENT.size * 64)
            except BlockingIOError:
                return events
            if not chunk:
                return events
            events.extend(self.parser.feed(chunk))

    def close(self) -> None:
        os.close(self.fd)
