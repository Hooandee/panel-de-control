"""Raw evdev input watch used to light the panel the moment the user touches the device.

Steam's activity signal arrives seconds late; the kernel sees touch, keys and (except on
the Steam Deck, whose controls Steam reads over hidraw) gamepad input immediately.
"""

import fcntl
import os
import select
import struct

EV_KEY = 0x01
EV_ABS = 0x03
EV_SW = 0x05
_EVENT = struct.Struct("llHHi")
_ABSINFO = struct.Struct("6i")
# Analog axes must travel this share of their range so stick drift never lights the panel.
_ABS_TRAVEL = 0.15


def _eviocgabs(code):
    return (2 << 30) | (_ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)


def _bits(text):
    value = 0
    for word in text.split():
        value = (value << 64) | int(word, 16)
    return value


def _watchable(sys_input, name):
    try:
        with open(os.path.join(sys_input, name, "device/capabilities/ev")) as f:
            ev = _bits(f.read())
    except (OSError, ValueError):
        return False
    return bool(ev & (1 << EV_KEY)) and not ev & (1 << EV_SW)


class InputWake:
    """Blocking: call `wait` off the event loop between `open` and `close`."""

    def __init__(self, dev_input="/dev/input", sys_input="/sys/class/input", ioctl=fcntl.ioctl):
        self._dev = dev_input
        self._sys = sys_input
        self._ioctl = ioctl
        self._fds = {}
        self._abs = {}

    def open(self):
        self.close()
        try:
            names = sorted(n for n in os.listdir(self._dev) if n.startswith("event"))
        except OSError:
            names = []
        for name in names:
            if not _watchable(self._sys, name):
                continue
            try:
                fd = os.open(os.path.join(self._dev, name), os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                with open(os.path.join(self._sys, name, "device/name")) as f:
                    label = f.read().strip()
            except OSError:
                label = name
            self._fds[fd] = label
        return len(self._fds)

    def close(self):
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds = {}
        self._abs = {}

    def _axis(self, fd, code):
        key = (fd, code)
        if key not in self._abs:
            try:
                buf = self._ioctl(fd, _eviocgabs(code), bytes(_ABSINFO.size))
                value, lo, hi = _ABSINFO.unpack(buf)[:3]
                self._abs[key] = (value, max(1, hi - lo))
            except OSError:
                self._abs[key] = None
        return self._abs[key]

    def _is_user_input(self, fd, kind, code, value):
        if kind == EV_KEY:
            return value == 1
        if kind == EV_ABS:
            axis = self._axis(fd, code)
            return axis is not None and abs(value - axis[0]) > axis[1] * _ABS_TRAVEL
        return False

    def wait(self, timeout):
        """Return the device label of the first deliberate input within `timeout`, else None."""
        if not self._fds:
            return None
        try:
            ready, _, _ = select.select(list(self._fds), [], [], timeout)
        except (OSError, ValueError):
            return None
        for fd in ready:
            try:
                data = os.read(fd, _EVENT.size * 64)
            except OSError:
                continue
            for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _, _, kind, code, value = _EVENT.unpack_from(data, offset)
                if self._is_user_input(fd, kind, code, value):
                    return self._fds[fd]
        return None
