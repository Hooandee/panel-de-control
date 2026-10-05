"""Game frame rate from gamescope's control protocol, the same per-frame timing the MangoHud overlay gets.

The stats FIFO's `fps=` is the compositor's repaint rate averaged over 300 repaints: it is not the
game's frame rate and goes silent whenever gamescope stops repainting. With the default
`mangoapp_use_output_timing`, gamescope hands mangoapp and `request_app_performance_stats` the very
same per-frame delta. Each answer clears the request, so asking again straight away catches every
frame (the deltas cover all of wall time and match mangoapp's own log), and frames over their summed
duration is the overlay's number.

The asking runs in a separate system python (this file with --child): inside the plugin the
interpreter is busy enough (and under FEX on ARM slow enough) that a thread re-asks late and loses the
short frames, reading 4-5 fps low. Never fork the plugin for this: a forked copy inherits Decky's
SIGTERM handler and runs the whole plugin unload, handing fans and power back to firmware.
"""

import glob
import os
import select
import shutil
import subprocess
import sys
import socket
import struct
import threading
import time
from collections import deque
from typing import Callable

# gamescope_control (protocol/gamescope-control.xml): request and event indices.
_REQ_TAKE_SCREENSHOT = 2
_REQ_APP_PERF_STATS = 6
_EVT_SCREENSHOT_TAKEN = 2
_SCREENSHOT_ALL_REAL_LAYERS = 2
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

    def close(self) -> None:
        self._sock.close()

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
        except (OSError, struct.error):
            sock.close()
            continue
        if connector is None or connector in skip:
            sock.close()
            continue
        return wire
    return None


def take_screenshot(path: str, root: str = "/", skip: frozenset[str] = frozenset(), timeout: float = 5.0) -> bool:
    # gamescope announces the result to every control client; Steam files it into the game's gallery.
    wire = _connect(root, set(skip))
    if wire is None:
        return False
    try:
        wire.send(_message(_CONTROL_ID, _REQ_TAKE_SCREENSHOT,
                           _wl_string(path) + struct.pack("<II", _SCREENSHOT_ALL_REAL_LAYERS, 0)))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for obj, opcode, data in wire.receive(max(0.0, end - time.monotonic())):
                if obj == _CONTROL_ID and opcode == _EVT_SCREENSHOT_TAKEN:
                    if _read_string(data, 0)[0] == path:
                        return True
        return False
    except (OSError, ConnectionError, struct.error):
        return False
    finally:
        wire.close()


def _ask(wire: _Wire, app_id: int) -> None:
    wire.send(_message(_CONTROL_ID, _REQ_APP_PERF_STATS, struct.pack("<I", app_id)))


Emit = Callable[[float, int, int], None]


def pump_frames(
    root: str, skip: set[str], app_id: Callable[[], int | None], emit: Emit, stopped: Callable[[], bool],
    tick: Callable[[], None] = lambda: None,
) -> None:
    """Ask for every frame of the app `app_id()` names until `stopped()`; reconnects as needed."""
    while not stopped():
        wire = _connect(root, skip)
        if wire is None:
            time.sleep(2.0)
            continue
        asked_for: int | None = None
        asked_at = 0.0
        try:
            while not stopped():
                tick()
                current = app_id()
                if not current:
                    asked_for = None
                    time.sleep(0.25)
                    continue
                if asked_for != current or time.monotonic() - asked_at > STALE_S:
                    _ask(wire, current)
                    asked_for, asked_at = current, time.monotonic()
                for obj, opcode, data in wire.receive(0.25):
                    if obj == _CONTROL_ID and opcode == _EVT_APP_PERF_STATS:
                        answered, lo, hi = struct.unpack_from("<III", data)
                        if answered == asked_for:
                            _ask(wire, current)
                            asked_at = time.monotonic()
                        emit(time.monotonic(), answered, hi << 32 | lo)
        except (OSError, ConnectionError, struct.error):
            pass
        finally:
            wire.close()
        time.sleep(1.0)


# The helper sums frames into short buckets so the plugin handles a few lines a second, not one per
# frame: parsing every frame cost the plugin about 10 % of a core under emulation at 40 fps.
FLUSH_S = 0.25


def _child_main(argv: list[str]) -> None:
    """stdin: one app id per line (0 = none); stdout: "<monotonic> <app id> <frames> <total ns>" per bucket."""
    root, skip = argv[0], set(argv[1:])
    state = {"app": None, "closed": False}
    bucket = {"app": None, "frames": 0, "total": 0, "since": time.monotonic()}

    def app_id() -> int | None:
        while select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if not line:
                state["closed"] = True
                break
            state["app"] = int(line) or None
        return state["app"]

    def flush(at: float) -> None:
        if bucket["frames"]:
            sys.stdout.write(f"{at:.6f} {bucket['app']} {bucket['frames']} {bucket['total']}\n")
            sys.stdout.flush()
        bucket.update(frames=0, total=0, since=at)

    def emit(at: float, app: int, frametime_ns: int) -> None:
        if app != bucket["app"]:
            flush(at)
            bucket["app"] = app
        bucket["frames"] += 1
        bucket["total"] += frametime_ns
        if at - bucket["since"] >= FLUSH_S:
            flush(at)

    def tick() -> None:
        now = time.monotonic()
        if now - bucket["since"] >= FLUSH_S:
            flush(now)

    try:
        pump_frames(root, skip, app_id, emit, lambda: state["closed"], tick)
    except (BrokenPipeError, KeyboardInterrupt):
        return


class GamescopePerf:
    """Frame rate of the focused app on the main gamescope display."""

    def __init__(
        self,
        app_id: Callable[[], int | None],
        skip_connectors: Callable[[], set[str]] = set,
        root: str = "/",
        clock: Callable[[], float] = time.monotonic,
        python: str | None = None,
        env: Callable[[], dict] | None = None,
        wrap: Callable[[list[str]], tuple[list[str], dict, dict] | None] | None = None,
    ):
        self._app_id = app_id
        self._skip_connectors = skip_connectors
        self._root = root
        self._clock = clock
        self._python = python if python is not None else shutil.which("python3", path="/usr/bin:/bin")
        self._env = env
        self._wrap = wrap
        self._frames: deque[tuple[float, int, int, int]] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None

    def _record(self, app_id: int, frametime_ns: int, at: float | None = None, frames: int = 1) -> None:
        now = self._clock() if at is None else at
        with self._lock:
            self._frames.append((now, app_id, frames, frametime_ns))
            while self._frames and now - self._frames[0][0] > WINDOW_S:
                self._frames.popleft()

    def _follow_child(self, process: subprocess.Popen) -> None:
        sent: int | None = None
        buffer = b""
        out = process.stdout.fileno()
        try:
            while not self._stop.is_set():
                current = self._app_id()
                if current != sent:
                    process.stdin.write(f"{current or 0}\n".encode())
                    process.stdin.flush()
                    sent = current
                if not select.select([out], [], [], 0.25)[0]:
                    continue
                chunk = os.read(out, 65536)
                if not chunk:
                    return
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    at, app, frames, total_ns = line.split()
                    self._record(int(app), int(total_ns), float(at), int(frames))
        except (OSError, ValueError):
            return

    def _spawn(self) -> subprocess.Popen | None:
        if not self._python:
            return None
        argv = [self._python, os.path.abspath(__file__), "--child", self._root, *sorted(self._skip_connectors())]
        wrapped = self._wrap(argv) if self._wrap else None
        command, env, identity = wrapped if wrapped else (argv, self._env() if self._env else None, {})
        try:
            return subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, close_fds=True, start_new_session=True, **identity,
            )
        except OSError:
            return None

    def start(self) -> None:
        """Idempotent; also brings back a reader whose helper died."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._reap()
        self._stop.clear()
        process = self._spawn()
        if process is not None:
            self._process = process
            target, args = self._follow_child, (process,)
        else:
            target = pump_frames
            args = (self._root, set(self._skip_connectors()), self._app_id,
                    lambda at, app, ft: self._record(app, ft, at), self._stop.is_set)
        self._thread = threading.Thread(target=target, args=args, daemon=True, name="gamescope-perf")
        self._thread.start()

    def _reap(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
            process.kill()
            process.wait(timeout=2.0)

    def stop(self) -> None:
        self._stop.set()
        self._reap()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if not thread.is_alive():
                self._thread = None
        with self._lock:
            self._frames.clear()

    def fps(self) -> float | None:
        """Frames per second over the last half second for the focused app, None when nothing recent."""
        app_id = self._app_id()
        now = self._clock()
        with self._lock:
            recent = [(n, ns) for at, app, n, ns in self._frames if app == app_id and now - at <= WINDOW_S]
            newest = self._frames[-1][0] if self._frames else None
        total_ns = sum(ns for _n, ns in recent)
        if not recent or newest is None or now - newest > STALE_S or total_ns <= 0:
            return None
        return sum(n for n, _ns in recent) * 1e9 / total_ns

    def diagnostics(self) -> dict:
        process = self._process
        return {"helper": bool(process and process.poll() is None), "python": self._python}


if __name__ == "__main__" and sys.argv[1:2] == ["--child"]:
    _child_main(sys.argv[2:])
