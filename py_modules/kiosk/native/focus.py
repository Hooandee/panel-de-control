import ctypes as C

# Steam's own UI (library, store, overlay).
STEAM_UI_APP = 769
_XA_CARDINAL = 6
_SUCCESS = 0


class FocusedApp:
    def __init__(self, display: str = ":0"):
        self._x = C.CDLL("libX11.so.6")
        self._x.XOpenDisplay.restype = C.c_void_p
        self._x.XOpenDisplay.argtypes = [C.c_char_p]
        self._x.XDefaultRootWindow.restype = C.c_ulong
        self._x.XDefaultRootWindow.argtypes = [C.c_void_p]
        self._x.XInternAtom.restype = C.c_ulong
        self._x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
        self._x.XGetWindowProperty.argtypes = [
            C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
            C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
            C.POINTER(C.c_void_p),
        ]
        self._x.XFree.argtypes = [C.c_void_p]
        self._display = self._x.XOpenDisplay(display.encode())
        if not self._display:
            raise OSError(f"cannot open X display {display}")
        self._root = self._x.XDefaultRootWindow(self._display)
        self._atom = self._x.XInternAtom(self._display, b"GAMESCOPE_FOCUSED_APP", 0)

    def read(self) -> int | None:
        kind, fmt, count, after = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
        data = C.c_void_p()
        status = self._x.XGetWindowProperty(
            self._display, self._root, self._atom, 0, 1, 0, _XA_CARDINAL,
            C.byref(kind), C.byref(fmt), C.byref(count), C.byref(after), C.byref(data),
        )
        try:
            if status != _SUCCESS or not data.value or count.value < 1 or fmt.value != 32:
                return None
            # Xlib hands 32-bit properties back as C longs.
            app = C.cast(data, C.POINTER(C.c_long))[0] & 0xFFFFFFFF
        finally:
            if data.value:
                self._x.XFree(data)
        return app if app and app != STEAM_UI_APP else None
