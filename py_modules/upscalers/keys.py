"""A short-lived virtual keyboard for OptiScaler's in-game hotkeys on handhelds without a keyboard.

OptiScaler only listens to keys: Insert opens its menu, End toggles frame generation, Page Up shows
its FPS counter, Page Down cycles the counter's style and, on builds with ReloadScaleShortcutKey,
Scroll Lock re-reads the scale and sharpness settings. Gamescope
picks up a new uinput keyboard like a plugged-in one, so the device lives just long enough to be
enumerated, press the key and go away.
"""

import fcntl
import os
import struct
import time

UINPUT = "/dev/uinput"
EV_SYN, EV_KEY, SYN_REPORT = 0x00, 0x01, 0x00
KEYS = {"menu": 110, "fg": 107, "fps": 104, "fps_style": 109, "home": 102, "reload": 70}  # INSERT, END, PAGEUP, PAGEDOWN, HOME, SCROLLLOCK
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
BUS_VIRTUAL = 0x06
ENUMERATE_S = 1.0
HOLD_S = 0.08
_EVENT = struct.Struct("llHHi")


class HotkeyError(Exception):
    pass


def _device_blob() -> bytes:
    name = b"Panel de Control keys".ljust(80, b"\0")
    ident = struct.pack("HHHH", BUS_VIRTUAL, 0x1209, 0x5044, 1)
    return name + ident + struct.pack("I", 0) + bytes(4 * 64 * 4)


def _emit(fd: int, kind: int, code: int, value: int) -> None:
    os.write(fd, _EVENT.pack(0, 0, kind, code, value))


def press(action: str, path: str = UINPUT, sleep=time.sleep) -> None:
    """Blocking (about a second): call it off the event loop."""
    code = KEYS.get(action)
    if code is None:
        raise HotkeyError("unknown_key")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as error:
        raise HotkeyError("no_uinput") from error
    try:
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)
        os.write(fd, _device_blob())
        fcntl.ioctl(fd, UI_DEV_CREATE)
        try:
            sleep(ENUMERATE_S)
            _emit(fd, EV_KEY, code, 1)
            _emit(fd, EV_SYN, SYN_REPORT, 0)
            sleep(HOLD_S)
            _emit(fd, EV_KEY, code, 0)
            _emit(fd, EV_SYN, SYN_REPORT, 0)
            sleep(HOLD_S)
        finally:
            fcntl.ioctl(fd, UI_DEV_DESTROY)
    except OSError as error:
        raise HotkeyError("uinput_failed") from error
    finally:
        os.close(fd)
