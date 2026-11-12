import ctypes
import ctypes.util
import os
import select
import struct

_IN_OPEN = 0x00000020
_IN_NONBLOCK = 0o4000
_IN_CLOEXEC = 0o2000000
_EVENT_HEADER = struct.Struct("iIII")


def _libc():
    name = ctypes.util.find_library("c")
    if not name:
        return None
    try:
        libc = ctypes.CDLL(name, use_errno=True)
        libc.inotify_init1.argtypes = [ctypes.c_int]
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        return libc
    except (OSError, AttributeError):
        return None


class OpenWatch:
    """Tells whether anything opened a file after the watch started.

    mangohudctl exits 0 whether or not mangoapp acted on the request; a reload
    that took effect re-reads presets.conf, so an open of that file is the
    delivery readback. `opened()` returns None when inotify is unavailable."""

    def __init__(self, path, libc_loader=_libc):
        self._fd = -1
        libc = libc_loader()
        if libc is None:
            return
        fd = libc.inotify_init1(_IN_NONBLOCK | _IN_CLOEXEC)
        if fd < 0:
            return
        if libc.inotify_add_watch(fd, os.fsencode(path), _IN_OPEN) < 0:
            os.close(fd)
            return
        self._fd = fd

    @property
    def available(self) -> bool:
        return self._fd >= 0

    def opened(self, timeout_s: float):
        if self._fd < 0:
            return None
        try:
            ready, _, _ = select.select([self._fd], [], [], max(0.0, timeout_s))
            if not ready:
                return False
            data = os.read(self._fd, 4096)
        except OSError:
            return None
        return len(data) >= _EVENT_HEADER.size

    def close(self) -> None:
        if self._fd >= 0:
            try:
                os.close(self._fd)
            finally:
                self._fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
