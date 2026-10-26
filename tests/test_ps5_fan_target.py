import os

from fans.ps5_target import Ps5FanTarget, FIRMWARE_DEFAULT_C, MAX_C, MIN_C


def _node(root, value="80"):
    path = os.path.join(root, "sys/bus/platform/devices/ps5-fan")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "target_temp"), "w") as handle:
        handle.write(f"{value}\n")
    return os.path.join(path, "target_temp")


def _read(path):
    with open(path) as handle:
        return handle.read().strip()


def test_absent_node_is_unsupported(tmp_path):
    target = Ps5FanTarget(root=str(tmp_path))
    assert target.supported is False
    assert target.state() == {"supported": False}
    assert target.apply(70)["ok"] is False


def test_state_reads_the_firmware_target(tmp_path):
    _node(str(tmp_path), "80")
    state = Ps5FanTarget(root=str(tmp_path)).state()
    assert state["supported"] is True
    assert state["celsius"] == 80
    assert state["min"] == MIN_C and state["max"] == MAX_C
    assert state["default"] == FIRMWARE_DEFAULT_C
    assert [p["id"] for p in state["presets"]] == ["quiet", "balanced", "cool", "max"]


def test_apply_writes_and_confirms(tmp_path):
    path = _node(str(tmp_path))
    result = Ps5FanTarget(root=str(tmp_path)).apply(65)
    assert result == {"ok": True, "celsius": 65, "detail": "applied"}
    assert _read(path) == "65"


def test_apply_clamps_to_the_safe_range(tmp_path):
    path = _node(str(tmp_path))
    target = Ps5FanTarget(root=str(tmp_path))
    assert target.apply(10)["celsius"] == MIN_C
    assert _read(path) == str(MIN_C)
    assert target.apply(100)["celsius"] == MAX_C
    assert _read(path) == str(MAX_C)


def test_readback_mismatch_is_not_success(tmp_path, monkeypatch):
    _node(str(tmp_path), "80")
    target = Ps5FanTarget(root=str(tmp_path))
    monkeypatch.setattr("ps5.firmware_io.FirmwareIo.write", lambda self, path, value: None)
    result = target.apply(60)
    assert result["ok"] is False
    assert result["celsius"] == 80
    assert result["detail"] == "readback_mismatch"


def test_write_failure_is_reported(tmp_path, monkeypatch):
    _node(str(tmp_path), "80")
    target = Ps5FanTarget(root=str(tmp_path))
    monkeypatch.setattr("ps5.firmware_io.FirmwareIo.write", lambda self, path, value: "errno_5")
    assert target.apply(60) == {"ok": False, "celsius": 80, "detail": "errno_5"}


def test_release_returns_the_firmware_default(tmp_path):
    path = _node(str(tmp_path), "55")
    assert Ps5FanTarget(root=str(tmp_path)).release()["ok"] is True
    assert _read(path) == str(FIRMWARE_DEFAULT_C)


def test_unreadable_target_reports_none(tmp_path):
    _node(str(tmp_path), "garbage")
    state = Ps5FanTarget(root=str(tmp_path)).state()
    assert state["supported"] is True
    assert state["celsius"] is None


class _SlowIo:
    def __init__(self):
        self.reads = 0

    def read(self, path):
        self.reads += 1
        return "80", None

    def write(self, path, value):
        return None

    def diagnostics(self):
        return {}


def test_state_reuses_the_last_read_between_refreshes(tmp_path):
    _node(str(tmp_path))
    now = [0.0]
    io = _SlowIo()
    target = Ps5FanTarget(root=str(tmp_path), io=io, clock=lambda: now[0])
    target.state()
    target.state()
    assert io.reads == 1
    now[0] = 11.0
    target.state()
    assert io.reads == 2


def test_stalled_firmware_link_times_out_and_cools_down(tmp_path):
    import threading
    from ps5.firmware_io import FirmwareIo

    gate = threading.Event()
    now = [0.0]
    io = FirmwareIo(timeout_s=0.05, cooldown_s=30.0, clock=lambda: now[0])
    value, error = io._call("read", "node", lambda: gate.wait(5))
    assert (value, error) == (None, "timeout")
    assert io._call("read", "node", lambda: "80") == (None, "cooldown")
    now[0] = 31.0
    assert io._call("read", "node", lambda: "80") == ("80", None)
    assert io.diagnostics()["timeouts"] == 1
    gate.set()


def test_firmware_not_ready_reports_its_errno(tmp_path):
    from ps5.firmware_io import FirmwareIo

    def not_ready():
        raise OSError(19, "No such device")

    io = FirmwareIo()
    assert io._call("write", "node", not_ready) == (None, "errno_19")
    assert io.last_error == {"op": "write", "path": "node", "error": "errno_19"}
