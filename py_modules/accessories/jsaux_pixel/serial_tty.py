"""The handful of termios calls the panel link needs.

Decky Loader 3.3 ships an embedded Python built without the ``termios`` extension, so importing it
stops the whole plugin. The standard module is used when present; otherwise the same calls go to
the kernel's own TCGETS/TCSETS ioctls (asm-generic layout, shared by x86_64 and aarch64). glibc's
cfsetspeed is skipped on purpose: from 2.42 it takes plain baud numbers instead of B* constants.
"""

import fcntl
import struct

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
    error = OSError

    B1000000 = 0o010010
    IGNPAR, CS8, CREAD, CLOCAL = 0o4, 0o60, 0o200, 0o4000
    VMIN, VTIME = 6, 5
    TCSANOW, TCIFLUSH = 0, 0
    TIOCEXCL = 0x540C
    _TCGETS, _TCSETS, _TCFLSH = 0x5401, 0x5402, 0x540B
    _CBAUD = 0o010017
    _NCCS = 19
    # struct termios: tcflag_t c_iflag, c_oflag, c_cflag, c_lflag; cc_t c_line; cc_t c_cc[19]
    _LAYOUT = struct.Struct(f"=4IB{_NCCS}B")

    def tcgetattr(fd: int) -> list:
        raw = bytearray(_LAYOUT.size)
        fcntl.ioctl(fd, _TCGETS, raw)
        iflag, oflag, cflag, lflag, _line, *cc = _LAYOUT.unpack(raw)
        speed = cflag & _CBAUD
        return [iflag, oflag, cflag, lflag, speed, speed, list(cc)]

    def tcsetattr(fd: int, when: int, values: list) -> None:
        if when != TCSANOW:
            raise ValueError("only TCSANOW is supported")
        iflag, oflag, cflag, lflag, _ispeed, ospeed, cc = values
        current = bytearray(_LAYOUT.size)
        fcntl.ioctl(fd, _TCGETS, current)
        line = _LAYOUT.unpack(current)[4]
        cflag = (cflag & ~_CBAUD) | (ospeed & _CBAUD)
        chars = (list(cc) + [0] * _NCCS)[:_NCCS]
        fcntl.ioctl(fd, _TCSETS, _LAYOUT.pack(iflag, oflag, cflag, lflag, line, *chars))

    def tcflush(fd: int, queue: int) -> None:
        fcntl.ioctl(fd, _TCFLSH, queue)
