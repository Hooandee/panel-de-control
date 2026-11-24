import json
from pathlib import Path

from fans.hwmon import FanReader


FIXTURE = json.loads((Path(__file__).parent / "data/ps5_hwmon_fan.json").read_text())


def _reported_chip(root):
    chip = root / "sys/class/hwmon/hwmon0"
    chip.mkdir(parents=True)
    (chip / "name").write_text(FIXTURE["chip"])
    for name, value in FIXTURE["values"].items():
        (chip / name).write_text(value)
    return chip


def test_reported_ps5_pwm_is_visible_without_rpm_or_control_writes(tmp_path):
    chip = _reported_chip(tmp_path)
    before = {p.name: p.read_text() for p in chip.iterdir()}

    state = FanReader(root=str(tmp_path), device_key=FIXTURE["device_key"]).read()

    assert state["fans"] == [{"label": "Fan 1", "rpm": None, "percent": 27,
                              "max_rpm": None, "duty_only": True}]
    assert {p.name: p.read_text() for p in chip.iterdir()} == before


def test_ps5_duty_monitor_requires_the_exact_device_and_chip(tmp_path):
    chip = _reported_chip(tmp_path)
    assert FanReader(root=str(tmp_path), device_key="steam_deck_lcd").read()["fans"] == []
    (chip / "name").write_text("another_pwm_chip")
    assert FanReader(root=str(tmp_path), device_key=FIXTURE["device_key"]).read()["fans"] == []


class _Io:
    def __init__(self):
        self.value = FIXTURE["values"]["pwm1"]
        self.error = None
        self.reads = []
        self.stuck = []

    def read(self, path):
        self.reads.append(path)
        return self.value, self.error

    def diagnostics(self):
        return {"stuck": list(self.stuck), "last_error": self.error}


def test_ps5_duty_caches_for_ten_seconds_and_never_reuses_a_failed_observation(tmp_path):
    from fans.ps5_duty import Ps5FanDuty

    _reported_chip(tmp_path)
    now = [0.0]
    io = _Io()
    reader = FanReader(root=str(tmp_path), device_key=FIXTURE["device_key"])
    reader._ps5_duty = Ps5FanDuty(io=io, clock=lambda: now[0])
    assert reader.read()["fans"][0]["percent"] == 27
    now[0] = 9.9
    assert reader.read()["fans"][0]["percent"] == 27
    assert len(io.reads) == 1
    now[0] = 10.0
    io.error = "timeout"
    state = reader.read()
    assert state["fans"] == [{"label": "Fan 1", "rpm": None, "percent": None,
                              "max_rpm": None, "duty_only": True}]
    assert state["duty_diagnostics"]["last_error"] == "timeout"
    assert reader.read()["fans"][0]["percent"] is None
    assert len(io.reads) == 2
    io.error = None
    for raw in ("256", "-1", "private text"):
        io.value = raw
        now[0] += 10
        assert reader.read()["fans"][0]["percent"] is None
    io.value = FIXTURE["values"]["pwm1"]
    now[0] += 10
    assert reader.read()["fans"][0]["percent"] == 27


def test_ps5_refresh_does_not_queue_concurrent_or_renumbered_firmware_reads():
    import threading
    from fans.ps5_duty import Ps5FanDuty

    now = [0.0]
    io = _Io()
    duty = Ps5FanDuty(io=io, clock=lambda: now[0])
    entered = threading.Event()
    release = threading.Event()
    result = []
    real_read = io.read

    def blocked(path):
        entered.set()
        assert release.wait(1)
        return real_read(path)

    io.read = blocked
    worker = threading.Thread(target=lambda: result.append(duty.read("old")))
    worker.start()
    try:
        assert entered.wait(1)
        assert duty.read("old") is None
    finally:
        release.set()
        worker.join(1)
    assert result == [69]
    assert io.reads == ["old"]
    io.read = real_read
    io.stuck = ["old"]
    now[0] = 10
    assert duty.read("new") is None
    assert io.reads == ["old"]
    io.stuck = []
    now[0] = 20
    assert duty.read("new") == 69
    assert io.reads == ["old", "new"]


def test_fan_rpc_keeps_the_event_loop_free_during_ps5_firmware_read(tmp_path, monkeypatch):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from test_fan_control_rpc import _make_plugin_fixture
    from fans.ps5_duty import Ps5FanDuty

    _reported_chip(tmp_path)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch)
    plugin = object.__new__(Plugin)
    plugin._init = lambda: None
    plugin._fan_reader = FanReader(root=str(tmp_path), device_key=FIXTURE["device_key"])
    pool = ThreadPoolExecutor(max_workers=1)
    plugin._apply_executor = pool
    release = threading.Event()

    async def run():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        loop_thread = threading.get_ident()
        io = _Io()

        def blocked(path):
            assert threading.get_ident() != loop_thread
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(1)
            return FIXTURE["values"]["pwm1"], None

        io.read = blocked
        plugin._fan_reader._ps5_duty = Ps5FanDuty(io=io)
        task = asyncio.create_task(plugin.get_fan_state())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not task.done()
        finally:
            release.set()
        return await asyncio.wait_for(task, 1)

    try:
        state = asyncio.run(run())
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert state["fans"][0]["percent"] == 27
