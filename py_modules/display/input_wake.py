"""Raw input watch for download mode: lights the panel the moment the user touches the
device and measures idleness without waiting for Steam's activity signal (seconds late).

The kernel exposes touch, keys and most handheld gamepads as evdev. The Steam Deck's
controls are only read by Steam over hidraw, so its controller reports are parsed too;
hidraw is not exclusive, Steam keeps receiving every report.
"""

import fcntl
import os
import select
import struct
import time

EV_KEY = 0x01
EV_ABS = 0x03
EV_SW = 0x05
BTN_JOYSTICK = 0x120
BTN_SOUTH = 0x130
_EVENT = struct.Struct("llHHi")
_ABSINFO = struct.Struct("6i")
# Analog axes must travel this share of their range so stick drift never counts as input.
_ABS_TRAVEL = 0.08
# Steam's own virtual gamepad mirrors input only for games; it proves nothing about coverage.
_STEAM_VIRTUAL_PAD = ("28de", "11ff")
_DECK_HID_ID = "000028DE:00001205"
_DECK_STATE = 0x09
_DECK_STICK_TRAVEL = int(32767 * _ABS_TRAVEL)
# The Deck controller streams ~250 reports/s even at rest; drain in batches instead of
# waking per report.
_HIDRAW_PACE_S = 0.05


def _eviocgabs(code):
    return (2 << 30) | (_ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)


def _bits(text):
    value = 0
    for word in text.split():
        value = (value << 64) | int(word, 16)
    return value


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def deck_report_input(report, previous):
    """(is_user_input, buttons) for one Steam Deck controller report. A newly pressed
    button or a stick/trigger pushed past the drift threshold counts; IMU never does."""
    if len(report) < 56 or report[2] != _DECK_STATE:
        return False, previous
    buttons = int.from_bytes(report[8:16], "little")
    if buttons & ~(previous or 0):
        return True, buttons
    triggers = struct.unpack_from("<2H", report, 44)
    sticks = struct.unpack_from("<4h", report, 48)
    pushed = any(abs(v) > _DECK_STICK_TRAVEL for v in sticks) or any(
        v > _DECK_STICK_TRAVEL for v in triggers)
    return pushed, buttons


class InputWake:
    """Blocking: call `wait` off the event loop between `open` and `close`."""

    def __init__(self, dev_input="/dev/input", sys_input="/sys/class/input",
                 sys_hidraw="/sys/class/hidraw", dev_root="/dev", ioctl=fcntl.ioctl,
                 clock=time.monotonic, sleep=time.sleep):
        self._dev = dev_input
        self._sys = sys_input
        self._sys_hidraw = sys_hidraw
        self._dev_root = dev_root
        self._ioctl = ioctl
        self._clock = clock
        self._sleep = sleep
        self._fds = {}
        self._hidraw = {}
        self._abs = {}
        self.gamepad = False

    def _open_evdev(self, name):
        base = os.path.join(self._sys, name, "device")
        try:
            ev = _bits(_read(os.path.join(base, "capabilities/ev")))
            keys = _bits(_read(os.path.join(base, "capabilities/key")) or "0")
        except ValueError:
            return
        if not ev & (1 << EV_KEY) or ev & (1 << EV_SW):
            return
        try:
            fd = os.open(os.path.join(self._dev, name), os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return
        self._fds[fd] = _read(os.path.join(base, "name")) or name
        vid_pid = (_read(os.path.join(base, "id/vendor")), _read(os.path.join(base, "id/product")))
        if keys & ((1 << BTN_SOUTH) | (1 << BTN_JOYSTICK)) and vid_pid != _STEAM_VIRTUAL_PAD:
            self.gamepad = True

    def _open_hidraw(self, name):
        if f"HID_ID=0003:{_DECK_HID_ID}" not in _read(os.path.join(self._sys_hidraw, name, "device/uevent")):
            return
        try:
            fd = os.open(os.path.join(self._dev_root, name), os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return
        self._hidraw[fd] = None
        self.gamepad = True

    def open(self):
        """Open every watchable device; returns how many."""
        self.close()
        for directory, opener in ((self._dev, self._open_evdev), (self._sys_hidraw, self._open_hidraw)):
            try:
                names = sorted(os.listdir(directory))
            except OSError:
                continue
            prefix = "event" if opener == self._open_evdev else "hidraw"
            for name in names:
                if name.startswith(prefix):
                    opener(name)
        return len(self._fds) + len(self._hidraw)

    def close(self):
        for fd in [*self._fds, *self._hidraw]:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds = {}
        self._hidraw = {}
        self._abs = {}
        self.gamepad = False

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

    def _evdev_input(self, fd):
        try:
            data = os.read(fd, _EVENT.size * 64)
        except OSError:
            return False
        for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
            _, _, kind, code, value = _EVENT.unpack_from(data, offset)
            if kind == EV_KEY and value == 1:
                return True
            if kind == EV_ABS:
                axis = self._axis(fd, code)
                if axis is not None and abs(value - axis[0]) > axis[1] * _ABS_TRAVEL:
                    return True
        return False

    def _hidraw_input(self, fd):
        found = False
        while True:
            try:
                report = os.read(fd, 64)
            except OSError:
                return found
            if not report:
                return found
            pressed, self._hidraw[fd] = deck_report_input(report, self._hidraw[fd])
            found = found or pressed

    def wait(self, timeout):
        """Return the label of the first deliberate input within `timeout`, else None."""
        fds = [*self._fds, *self._hidraw]
        if not fds:
            return None
        deadline = self._clock() + timeout
        while True:
            remaining = deadline - self._clock()
            try:
                ready, _, _ = select.select(fds, [], [], max(0.0, remaining))
            except (OSError, ValueError):
                return None
            for fd in ready:
                if fd in self._fds and self._evdev_input(fd):
                    return self._fds[fd]
                if fd in self._hidraw and self._hidraw_input(fd):
                    return "Steam Deck controller"
            if self._clock() >= deadline:
                return None
            if any(fd in self._hidraw for fd in ready):
                self._sleep(_HIDRAW_PACE_S)
