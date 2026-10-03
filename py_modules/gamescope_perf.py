"""Game frame rate from gamescope's control protocol, the same per-frame timing the MangoHud overlay gets.

The stats FIFO's `fps=` is the compositor's repaint rate averaged over 300 repaints: it is not the
game's frame rate and goes silent whenever gamescope stops repainting. With the default
`mangoapp_use_output_timing`, gamescope hands mangoapp and `request_app_performance_stats` the very
same per-frame delta. Each answer clears the request, so asking again straight away catches every
frame (measured on the AYN Thor: the deltas cover 100 % of wall time and match mangoapp's own log), and
frames over their summed duration is the overlay's number.

The asking runs in its own process: inside the plugin, the interpreter is busy enough (and under FEX
on ARM slow enough) that a thread re-asks late and loses the short frames, reading 4-5 fps low.
"""

import glob
import multiprocessing
import os
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

# Same window MangoHud uses (fps_sampling_period, 500 ms) so the overlay and the bottom screen agree.
WINDOW_S = 0.5
STALE_S = 2.0


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
    total = sum(frametimes_ns)
    return len(frametimes_ns) * 1e9 / total if total > 0 else None


def _sockets(root: str) -> list[str]:
    paths = glob.glob(os.path.join(root, "run/user/*/gamescope-[0-9]*"))
    return sorted(p for p in paths if not p.endswith((".lock", "-ei")))


def _connect(root: str, skip: set[str]) -> _Wire | None:
    for path in _sockets(root):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(path)
            wire = _Wire(sock)
            connector = bind_control(wire)
        except OSError:
            sock.close()
            continue
        if connector is None or connector in skip:
            sock.close()
            continue
        return wire
    return None


def _ask(wire: _Wire, app_id: int) -> None:
    wire.send(_message(_CONTROL_ID, _REQ_APP_PERF_STATS, struct.pack("<I", app_id)))


def _child_pump(conn, wire: _Wire, app_id: int | None) -> int | None:
    asked_for: int | None = None
    asked_at = 0.0
    while True:
        while conn.poll(0):
            app_id = conn.recv()
        if not app_id:
            asked_for = None
            conn.poll(0.5)
            continue
        if asked_for != app_id or time.monotonic() - asked_at > STALE_S:
            _ask(wire, app_id)
            asked_for, asked_at = app_id, time.monotonic()
        for obj, opcode, data in wire.receive(0.5):
            if obj == _CONTROL_ID and opcode == _EVT_APP_PERF_STATS:
                answered, lo, hi = struct.unpack_from("<III", data)
                if answered == asked_for:
                    _ask(wire, app_id)
                    asked_at = time.monotonic()
                conn.send((time.monotonic(), answered, hi << 32 | lo))


def _child_main(conn, root: str, skip: set[str]) -> None:
    """Ask for every frame of the app the parent names; exits when the parent goes away."""
    app_id: int | None = None
    try:
        while True:
            wire = _connect(root, skip)
            if wire is None:
                if conn.poll(2.0):
                    app_id = conn.recv()
                continue
            try:
                app_id = _child_pump(conn, wire, app_id)
            except (OSError, ConnectionError, struct.error):
                pass
            finally:
                wire._sock.close()
            time.sleep(1.0)
    except (EOFError, BrokenPipeError, KeyboardInterrupt):
        return


class GamescopePerf:
    """Frame rate of the focused app on the main gamescope display, read by a helper process."""

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
        self._process = None

    def _record(self, app_id: int, frametime_ns: int, at: float | None = None) -> None:
        now = self._clock() if at is None else at
        with self._lock:
            self._frames.append((now, app_id, frametime_ns))
            while self._frames and now - self._frames[0][0] > WINDOW_S:
                self._frames.popleft()

    def _drain(self, conn) -> None:
        sent: int | None = None
        try:
            while not self._stop.is_set():
                app_id = self._app_id()
                if app_id != sent:
                    conn.send(app_id)
                    sent = app_id
                while conn.poll(0.25):
                    at, answered, frametime_ns = conn.recv()
                    self._record(answered, frametime_ns, at)
        except (EOFError, OSError):
            return

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # fork: the plugin runs inside Decky's frozen loader, which cannot re-launch a Python interpreter.
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe()
        self._process = context.Process(
            target=_child_main, args=(child, self._root, set(self._skip_connectors())),
            daemon=True, name="gamescope-perf",
        )
        self._process.start()
        child.close()
        self._thread = threading.Thread(target=self._drain, args=(parent,), daemon=True, name="gamescope-perf")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if not thread.is_alive():
                self._thread = None
        process = self._process
        if process is not None:
            process.terminate()
            process.join(timeout=2.0)
            self._process = None
        with self._lock:
            self._frames.clear()

    def fps(self) -> float | None:
        """Frames per second over the last half second for the focused app, None when nothing recent."""
        app_id = self._app_id()
        now = self._clock()
        with self._lock:
            times = [ft for at, app, ft in self._frames if app == app_id and now - at <= WINDOW_S]
            newest = self._frames[-1][0] if self._frames else None
        if not times or newest is None or now - newest > STALE_S:
            return None
        return frame_rate(times)

    def diagnostics(self) -> dict:
        process = self._process
        return {"alive": bool(process and process.is_alive())}
