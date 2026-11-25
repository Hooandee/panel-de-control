"""The handful of termios calls the panel link needs.

Decky Loader 3.3 ships an embedded Python built without the ``termios`` extension, so importing it
stops the whole plugin. The standard module is used when present; otherwise the same calls go
straight to libc through ctypes (Linux ABI, identical on x86_64 and aarch64).
"""

import ctypes
import ctypes.util
import os

try:
    import termios as _termios
except ImportError:
    _termios = None

if _termios is not None:
    error = _termios.error
    B1000000 = getattr(_termios, "B1000000", 0o010010)
    IGNPAR, CS8, CREAD, CLOCAL = _termios.IGNPAR, _termios.CS8, _termios.CREAD, _termios.CLOCAL
    VMIN, VTIME = _termios.VMIN, _termios.VTIME
    TCSANOW, TCIFLUSH, TIOCEXCL = _termios.TCSANOW, _termios.TCIFLUSH, _termios.TIOCEXCL
    tcgetattr, tcsetattr, tcflush = _termios.tcgetattr, _termios.tcsetattr, _termios.tcflush
else:

    class error(Exception):  # noqa: N801 - mirrors termios.error
        pass

    B1000000 = 0o010010
    IGNPAR, CS8, CREAD, CLOCAL = 0o4, 0o60, 0o200, 0o4000
    VMIN, VTIME = 6, 5
    TCSANOW, TCIFLUSH = 0, 0
    TIOCEXCL = 0x540C
    _NCCS = 32

    class _Termios(ctypes.Structure):
        _fields_ = [
            ("c_iflag", ctypes.c_uint), ("c_oflag", ctypes.c_uint), ("c_cflag", ctypes.c_uint),
            ("c_lflag", ctypes.c_uint), ("c_line", ctypes.c_ubyte), ("c_cc", ctypes.c_ubyte * _NCCS),
            ("c_ispeed", ctypes.c_uint), ("c_ospeed", ctypes.c_uint),
        ]

    _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

    def _check(result: int) -> None:
        if result != 0:
            code = ctypes.get_errno()
            raise error(code, os.strerror(code))

    def tcgetattr(fd: int) -> list:
        attrs = _Termios()
        _check(_libc.tcgetattr(fd, ctypes.byref(attrs)))
        return [attrs.c_iflag, attrs.c_oflag, attrs.c_cflag, attrs.c_lflag,
                _libc.cfgetispeed(ctypes.byref(attrs)), _libc.cfgetospeed(ctypes.byref(attrs)), list(attrs.c_cc)]

    def tcsetattr(fd: int, when: int, values: list) -> None:
        attrs = _Termios()
        _check(_libc.tcgetattr(fd, ctypes.byref(attrs)))
        attrs.c_iflag, attrs.c_oflag, attrs.c_cflag, attrs.c_lflag = values[:4]
        for index, value in enumerate(values[6][:_NCCS]):
            attrs.c_cc[index] = value
        _check(_libc.cfsetispeed(ctypes.byref(attrs), values[4]))
        _check(_libc.cfsetospeed(ctypes.byref(attrs), values[5]))
        _check(_libc.tcsetattr(fd, when, ctypes.byref(attrs)))

    def tcflush(fd: int, queue: int) -> None:
        _check(_libc.tcflush(fd, queue))
