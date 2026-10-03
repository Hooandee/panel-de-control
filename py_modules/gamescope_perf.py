"""Game frame rate from gamescope's control protocol: the focused app's own present-to-present time.

The stats FIFO's `fps=` is the compositor's repaint rate averaged over 300 repaints: it is not the
game's frame rate and goes silent whenever gamescope stops repainting. `request_app_performance_stats`
answers with the delta between the app's next present and the one before it.

Re-asking right after an answer misses the short frames that land inside the round trip, so the
rate read low (60 for a game alternating 8 ms and 16 ms frames on a 120 Hz panel). Asking at a random
moment instead lands inside each frame in proportion to its length, and the mean of 1/frametime over
such samples is exactly frames per second whatever the mix.

gamescope's mangoapp overlay defaults to output timing (`mangoapp_use_output_timing`), which counts
screen updates rather than game frames; on a 120 Hz panel it reads above a game locked at 60.
"""

import glob
import os
import random
import socket
import struct
import threading
import time
from collections import deque
from typing import Callable

# gamescope_control (protocol/gamescope-control.xml): request and event indices.
_REQ_APP_PERF_STATS = 6
_EVT_ACTIVE_DISPLAY_INFO = 1
_EVT_APP_PERF_STATS = 3
_MIN_VERSION = 6

_DISPLAY_ID = 1
_REGISTRY_ID = 2
_SYNC_ID = 3
_CONTROL_ID = 4

WINDOW_S = 2.0
STALE_S = 2.0
# Longest random wait before the next question; longer than a 30 fps frame keeps the phase uniform.
ASK_JITTER_S = 0.05


def _message(obj: int, opcode: int, payload: bytes = b"") -> bytes:
    return struct.pack("<IHH", obj, opcode, 8 + len(payload)) + payload


def _wl_string(text: str) -> bytes:
    raw = text.encode() + b"\0"
    return struct.pack("<I", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def _read_string(data: bytes, offset: int) -> tuple[str, int]:
    (length,) = struct.unpack_from("<I", data, offset)
    text = data[offset + 4: offset + 4 + max(0, length - 1)].decode(errors="replace")
    return text, offset + 4 + ((length + 3) & ~3)


class _Wire:
    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._buffer = b""

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def receive(self, timeout: float) -> list[tuple[int, int, bytes]]:
        self._sock.settimeout(timeout)
        try:
            chunk = self._sock.recv(65536)
        except socket.timeout:
            return []
        if not chunk:
            raise ConnectionError("gamescope closed the connection")
        self._buffer += chunk
        events = []
        while len(self._buffer) >= 8:
            obj, opcode, size = struct.unpack_from("<IHH", self._buffer)
            if size < 8 or len(self._buffer) < size:
                break
            events.append((obj, opcode, self._buffer[8:size]))
            self._buffer = self._buffer[size:]
        return events


def bind_control(wire: _Wire, timeout: float = 2.0) -> str | None:
    """Bind gamescope_control; returns the connector it drives, or None if the protocol is too old."""
    wire.send(_message(_DISPLAY_ID, 1, struct.pack("<I", _REGISTRY_ID)))
    wire.send(_message(_DISPLAY_ID, 0, struct.pack("<I", _SYNC_ID)))
    control = None
    deadline = time.monotonic() + timeout
    synced = False
    while not synced and time.monotonic() < deadline:
        for obj, opcode, data in wire.receive(0.5):
            if obj == _REGISTRY_ID and opcode == 0:
                (name,) = struct.unpack_from("<I", data)
                interface, offset = _read_string(data, 4)
                (version,) = struct.unpack_from("<I", data, offset)
                if interface == "gamescope_control":
                    control = (name, version)
            elif obj == _SYNC_ID:
                synced = True
    if control is None or control[1] < _MIN_VERSION:
        return None
    name, version = control
    wire.send(_message(
        _REGISTRY_ID, 0,
        struct.pack("<I", name) + _wl_string("gamescope_control") + struct.pack("<II", min(version, 7), _CONTROL_ID),
    ))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for obj, opcode, data in wire.receive(0.5):
            if obj == _CONTROL_ID and opcode == _EVT_ACTIVE_DISPLAY_INFO:
                return _read_string(data, 0)[0]
    return ""


def frame_rate(frametimes_ns: list[int]) -> float | None:
    """Frames per second from frametimes sampled at random moments (see module docstring)."""
    rates = [1e9 / ft for ft in frametimes_ns if ft > 0]
    return sum(rates) / len(rates) if rates else None


class GamescopePerf:
    """Background reader of the focused app's frame rate on the main gamescope display."""

    def __init__(
        self,
        app_id: Callable[[], int | None],
        skip_connectors: Callable[[], set[str]] = set,
        root: str = "/",
        clock: Callable[[], float] = time.monotonic,
    ):
        self._app_id = app_id
        self._skip_connectors = skip_connectors
        self._root = root
        self._clock = clock
        self._frames: deque[tuple[float, int, int]] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None

    def _sockets(self) -> list[str]:
        paths = glob.glob(os.path.join(self._root, "run/user/*/gamescope-[0-9]*"))
        return sorted(p for p in paths if not p.endswith((".lock", "-ei")))

    def _connect(self) -> _Wire | None:
        skip = self._skip_connectors()
        for path in self._sockets():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(path)
                wire = _Wire(sock)
                connector = bind_control(wire)
            except OSError as error:
                sock.close()
                self._last_error = f"connect:{type(error).__name__}"
                continue
            if connector is None or connector in skip:
                sock.close()
                continue
            return wire
        return None

    def _record(self, app_id: int, frametime_ns: int) -> None:
        now = self._clock()
        with self._lock:
            self._frames.append((now, app_id, frametime_ns))
            while self._frames and now - self._frames[0][0] > WINDOW_S:
                self._frames.popleft()

    def _run(self) -> None:
        while not self._stop.is_set():
            wire = self._connect()
            if wire is None:
                self._stop.wait(2.0)
                continue
            try:
                self._pump(wire)
            except (OSError, ConnectionError, struct.error) as error:
                self._last_error = f"read:{type(error).__name__}"
            finally:
                wire._sock.close()
            self._stop.wait(1.0)

    def _pump(self, wire: _Wire) -> None:
        asked_for: int | None = None
        asked_at = 0.0
        ask_after: float | None = 0.0
        while not self._stop.is_set():
            app_id = self._app_id()
            if not app_id:
                asked_for = None
                ask_after = 0.0
                self._stop.wait(0.5)
                continue
            now = self._clock()
            waiting = asked_for == app_id and now - asked_at <= STALE_S
            if not waiting and (ask_after is None or now >= ask_after):
                wire.send(_message(_CONTROL_ID, _REQ_APP_PERF_STATS, struct.pack("<I", app_id)))
                asked_for, asked_at, ask_after = app_id, now, None
            timeout = 0.5 if ask_after is None else max(0.001, min(0.5, ask_after - now))
            for obj, opcode, data in wire.receive(timeout):
                if obj == _CONTROL_ID and opcode == _EVT_APP_PERF_STATS:
                    answered, lo, hi = struct.unpack_from("<III", data)
                    self._record(answered, hi << 32 | lo)
                    if answered == asked_for:
                        asked_for = None
                        ask_after = self._clock() + random.uniform(0.0, ASK_JITTER_S)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="gamescope-perf")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if not thread.is_alive():
                self._thread = None
        with self._lock:
            self._frames.clear()

    def fps(self) -> float | None:
        """Frames per second over the last two seconds for the focused app, None when nothing recent."""
        app_id = self._app_id()
        now = self._clock()
        with self._lock:
            times = [ft for at, app, ft in self._frames if app == app_id and now - at <= WINDOW_S]
            newest = self._frames[-1][0] if self._frames else None
        if not times or newest is None or now - newest > STALE_S:
            return None
        return frame_rate(times)

    def diagnostics(self) -> dict:
        thread = self._thread
        return {"alive": bool(thread and thread.is_alive()), "last_error": self._last_error}
