"""Raw input watch that lights the panel without waiting for Steam's activity signal (seconds
late). Touch, keys and most handheld pads are evdev. Valve-protocol controllers (Steam Deck,
Legion Go S) are read by Steam over hidraw while their evdev node stays silent, so their state
reports are parsed too; hidraw is not exclusive. Blocking: call off the event loop."""

import fcntl
import os
import select
import struct
import threading
import time

EV_KEY, EV_ABS, EV_SW = 0x01, 0x03, 0x05
_EVENT = struct.Struct("llHHi")
_ABSINFO = struct.Struct("6i")
# Share of an axis' range a stick must travel, so drift never counts as input.
_TRAVEL = 0.08
_VALVE_HID = "HID_ID=0003:000028DE:"
_VALVE_STATE = 0x09
# Valve controllers stream ~250 reports/s at rest: drain in batches, not per report.
_HIDRAW_PACE_S = 0.05


def _eviocgabs(code):
    return (2 << 30) | (_ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def valve_report_input(report, previous):
    """(is_input, buttons): a newly pressed button or a pushed stick/trigger; never the IMU.
    The first report after opening is only the baseline, so a held button or a resting thumb on
    a capacitive stick never counts on every rescan."""
    if len(report) < 56 or report[2] != _VALVE_STATE:
        return False, previous
    buttons = int.from_bytes(report[8:16], "little")
    if previous is None:
        return False, buttons
    limit = 32767 * _TRAVEL
    pushed = any(abs(v) > limit for v in struct.unpack_from("<4h", report, 48)) or any(
        v > limit for v in struct.unpack_from("<2H", report, 44))
    return bool(buttons & ~(previous or 0)) or pushed, buttons


class InputWake:
    def __init__(self, dev="/dev", sys_class="/sys/class", ioctl=fcntl.ioctl, sleep=time.sleep):
        self._dev = dev
        self._sys = sys_class
        self._ioctl = ioctl
        self._sleep = sleep
        self._evdev = {}
        self._hidraw = {}
        self._axes = {}
        # `close` from the event loop must not pull fds out from under a running `wait`.
        self._lock = threading.Lock()

    def _open(self, path):
        try:
            return os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return None

    def open(self):
        with self._lock:
            self._close()
            inputs = os.path.join(self._sys, "input")
            for name in sorted(os.listdir(inputs)) if os.path.isdir(inputs) else []:
                base = os.path.join(inputs, name, "device")
                try:
                    ev = int(_read(os.path.join(base, "capabilities/ev")).split()[-1], 16)
                except (IndexError, ValueError):
                    continue
                if name.startswith("event") and ev & (1 << EV_KEY) and not ev & (1 << EV_SW):
                    fd = self._open(os.path.join(self._dev, "input", name))
                    if fd is not None:
                        self._evdev[fd] = _read(os.path.join(base, "name")) or name
            hid = os.path.join(self._sys, "hidraw")
            for name in sorted(os.listdir(hid)) if os.path.isdir(hid) else []:
                if _VALVE_HID in _read(os.path.join(hid, name, "device/uevent")):
                    fd = self._open(os.path.join(self._dev, name))
                    if fd is not None:
                        self._hidraw[fd] = None
            return len(self._evdev) + len(self._hidraw)

    def close(self):
        with self._lock:
            self._close()

    def _close(self):
        for fd in [*self._evdev, *self._hidraw]:
            self._drop(fd)

    def _drop(self, fd):
        self._evdev.pop(fd, None)
        self._hidraw.pop(fd, None)
        self._axes = {k: v for k, v in self._axes.items() if k[0] != fd}
        try:
            os.close(fd)
        except OSError:
            pass

    def _reads(self, fd, size):
        """Yield pending chunks; an unplugged node (readable forever) is dropped, not spun on."""
        while True:
            try:
                data = os.read(fd, size)
            except BlockingIOError:
                return
            except OSError:
                self._drop(fd)
                return
            if not data:
                return
            yield data

    def _axis_moved(self, fd, code, value):
        if (fd, code) not in self._axes:
            try:
                rest, lo, hi = _ABSINFO.unpack(self._ioctl(fd, _eviocgabs(code), bytes(_ABSINFO.size)))[:3]
                self._axes[(fd, code)] = (rest, max(1, hi - lo))
            except OSError:
                self._axes[(fd, code)] = None
        axis = self._axes[(fd, code)]
        return axis is not None and abs(value - axis[0]) > axis[1] * _TRAVEL

    def _evdev_input(self, fd):
        for data in self._reads(fd, _EVENT.size * 64):
            for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _, _, kind, code, value = _EVENT.unpack_from(data, offset)
                if (kind == EV_KEY and value == 1) or (kind == EV_ABS and self._axis_moved(fd, code, value)):
                    return True
        return False

    def _hidraw_input(self, fd):
        found = False
        for report in self._reads(fd, 64):
            pressed, self._hidraw[fd] = valve_report_input(report, self._hidraw.get(fd))
            found = found or pressed
        return found

    def wait(self, timeout):
        """Label of the first deliberate input within `timeout`, else None."""
        with self._lock:
            deadline = time.monotonic() + timeout
            while True:
                fds = [*self._evdev, *self._hidraw]
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    ready = select.select(fds, [], [], remaining)[0] if fds else None
                except (OSError, ValueError):
                    ready = None
                if ready is None:
                    self._sleep(remaining)
                    return None
                for fd in ready:
                    if fd in self._evdev and self._evdev_input(fd):
                        return self._evdev.get(fd, "input")
                    if fd in self._hidraw and self._hidraw_input(fd):
                        return "Valve controller"
                if time.monotonic() >= deadline:
                    return None
                if any(fd in self._hidraw for fd in ready):
                    self._sleep(_HIDRAW_PACE_S)
