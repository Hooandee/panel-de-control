import pathlib
import shutil
import socket
import tempfile
import struct
import threading
import time

import pytest

import gamescope_perf as gp


@pytest.fixture
def short_root():
    # AF_UNIX paths are capped near 104 bytes on macOS; pytest's tmp_path is longer.
    root = tempfile.mkdtemp(prefix="gp", dir="/tmp")
    yield pathlib.Path(root)
    shutil.rmtree(root, ignore_errors=True)


def _event(obj, opcode, payload=b""):
    return struct.pack("<IHH", obj, opcode, 8 + len(payload)) + payload


class FakeGamescope:
    """Speaks just enough wl_display/wl_registry/gamescope_control for the reader."""

    def __init__(self, path, connector="DSI-2", version=7, frametimes_ns=(16_666_667,), app_id=4242):
        self.connector = connector
        self.version = version
        self.frametimes = list(frametimes_ns)
        self.app_id = app_id
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(4)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        buffer = b""
        sent = 0
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buffer += chunk
                while len(buffer) >= 8:
                    obj, opcode, size = struct.unpack_from("<IHH", buffer)
                    data, buffer = buffer[8:size], buffer[size:]
                    if obj == 1 and opcode == 1:
                        registry = struct.unpack_from("<I", data)[0]
                        conn.sendall(_event(registry, 0, struct.pack("<I", 11) + gp._wl_string("gamescope_control") + struct.pack("<I", self.version)))
                    elif obj == 1 and opcode == 0:
                        conn.sendall(_event(struct.unpack_from("<I", data)[0], 0, struct.pack("<I", 0)))
                    elif obj == 2 and opcode == 0:
                        new_id = struct.unpack_from("<I", data, len(data) - 4)[0]
                        conn.sendall(_event(new_id, gp._EVT_ACTIVE_DISPLAY_INFO, gp._wl_string(self.connector) + gp._wl_string("x") * 2 + struct.pack("<I", 0) + struct.pack("<I", 0)))
                    elif obj == gp._CONTROL_ID and opcode == gp._REQ_APP_PERF_STATS:
                        app = struct.unpack_from("<I", data)[0]
                        self.requests.append(app)
                        if app == self.app_id and sent < len(self.frametimes):
                            ft = self.frametimes[sent]
                            sent += 1
                            conn.sendall(_event(gp._CONTROL_ID, gp._EVT_APP_PERF_STATS, struct.pack("<III", app, ft & 0xFFFFFFFF, ft >> 32)))
        except OSError:
            return

    def close(self):
        self.server.close()


def _socket_dir(tmp_path):
    run = tmp_path / "run/user/1000"
    run.mkdir(parents=True)
    return run


def test_frame_rate_is_frames_over_their_duration():
    # Odyssey on the Thor: uneven frames, mangoapp's log said ~12 fps; a mean of 1/frametime said 36.
    frames = [20_000_000, 150_000_000, 20_000_000, 140_000_000, 30_000_000, 140_000_000]
    assert round(gp.frame_rate(frames), 1) == 12.0
    assert gp.frame_rate([]) is None


def test_keeps_asking_for_the_focused_app(short_root):
    run = _socket_dir(short_root)
    fake = FakeGamescope(str(run / "gamescope-0"), frametimes_ns=[71_428_571] * 10)
    perf = gp.GamescopePerf(app_id=lambda: 4242, root=str(short_root))
    perf.start()
    try:
        deadline = time.monotonic() + 3
        while fake.requests.count(4242) < 4 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake.requests.count(4242) >= 4
        assert round(perf.fps()) == 14
    finally:
        perf.stop()
        fake.close()


def test_skips_the_bottom_screen_compositor(short_root):
    run = _socket_dir(short_root)
    bottom = FakeGamescope(str(run / "gamescope-0"), connector="DSI-1")
    main = FakeGamescope(str(run / "gamescope-1"), connector="DSI-2", frametimes_ns=[8_333_333] * 20)
    perf = gp.GamescopePerf(app_id=lambda: 4242, skip_connectors=lambda: {"DSI-1"}, root=str(short_root))
    perf.start()
    try:
        deadline = time.monotonic() + 3
        while perf.fps() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert round(perf.fps()) == 120
        assert bottom.requests == []
    finally:
        perf.stop()
        bottom.close()
        main.close()


def test_old_gamescope_without_perf_query_is_left_alone(short_root):
    run = _socket_dir(short_root)
    fake = FakeGamescope(str(run / "gamescope-0"), version=5)
    perf = gp.GamescopePerf(app_id=lambda: 4242, root=str(short_root))
    perf.start()
    try:
        time.sleep(0.5)
        assert perf.fps() is None
        assert fake.requests == []
    finally:
        perf.stop()
        fake.close()


def test_no_frames_means_no_reading(tmp_path):
    now = [100.0]
    perf = gp.GamescopePerf(app_id=lambda: 7, root=str(tmp_path), clock=lambda: now[0])
    perf._record(7, 16_666_667)
    assert round(perf.fps()) == 60
    now[0] += gp.STALE_S + 0.1
    assert perf.fps() is None
