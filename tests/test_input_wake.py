import struct

import display.input_wake as iw
from display.input_wake import EV_ABS, EV_KEY, InputWake, valve_report_input

_EVENT = struct.Struct("llHHi")
ABS_X, BTN_SOUTH, BTN_TOUCH = 0x00, 0x130, 0x14A


def _evdev(tmp_path, name, label, ev_bits, events=()):
    base = tmp_path / "sys" / "input" / name / "device"
    (base / "capabilities").mkdir(parents=True)
    (base / "capabilities" / "ev").write_text(f"{ev_bits:x}\n")
    (base / "name").write_text(label + "\n")
    (tmp_path / "dev" / "input").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dev" / "input" / name).write_bytes(b"".join(_EVENT.pack(0, 0, *e) for e in events))


def _report(buttons=0, sticks=(0, 0, 0, 0), triggers=(0, 0), imu=0):
    r = bytearray(64)
    r[0], r[2], r[3] = 0x01, 0x09, 0x40
    r[8:16] = buttons.to_bytes(8, "little")
    struct.pack_into("<6h", r, 24, *([imu] * 6))
    struct.pack_into("<2H", r, 44, *triggers)
    struct.pack_into("<4h", r, 48, *sticks)
    return bytes(r)


def _hidraw(tmp_path, name, hid_id, reports=()):
    node = tmp_path / "sys" / "hidraw" / name / "device"
    node.mkdir(parents=True)
    (node / "uevent").write_text(f"HID_ID=0003:{hid_id}\n")
    (tmp_path / "dev").mkdir(exist_ok=True)
    (tmp_path / "dev" / name).write_bytes(b"".join(reports))


def _watch(tmp_path, slept=None):
    absinfo = struct.Struct("6i").pack(0, -32768, 32767, 0, 0, 0)
    return InputWake(str(tmp_path / "dev"), str(tmp_path / "sys"), ioctl=lambda *a: absinfo,
                     sleep=(slept.append if slept is not None else lambda s: None))


def test_touch_press_wakes_but_a_release_does_not(tmp_path):
    _evdev(tmp_path, "event7", "FTS3528", 0x1B, [(EV_KEY, BTN_TOUCH, 1)])
    _evdev(tmp_path, "event2", "pad", 0x20000B, [(EV_KEY, BTN_SOUTH, 0)])
    watch = _watch(tmp_path)
    assert watch.open() == 2
    assert watch.wait(0) == "FTS3528"


def test_stick_drift_is_ignored_but_a_push_counts(tmp_path):
    _evdev(tmp_path, "event2", "drifting", 0x20000B, [(EV_ABS, ABS_X, 2000)])
    _evdev(tmp_path, "event3", "pushed", 0x20000B, [(EV_ABS, ABS_X, 20000)])
    watch = _watch(tmp_path)
    watch.open()
    assert watch.wait(0) == "pushed"


def test_switches_and_keyless_sensors_are_not_watched(tmp_path):
    _evdev(tmp_path, "event1", "Lid Switch", 0x21, [(EV_KEY, 0, 1)])
    _evdev(tmp_path, "event5", "IMU", 0x9, [(EV_ABS, ABS_X, 30000)])
    assert _watch(tmp_path).open() == 0


def test_valve_controllers_wake_on_press_and_push_not_at_rest(tmp_path):
    _hidraw(tmp_path, "hidraw2", "000028DE:00001205", [_report(imu=v, sticks=(800, -900, 0, 0)) for v in (100, -2000)])
    _hidraw(tmp_path, "hidraw1", "00002808:00001015", [_report(buttons=1)])
    watch = _watch(tmp_path)
    assert watch.open() == 1 and watch.wait(0) is None
    (tmp_path / "dev" / "hidraw2").write_bytes(_report() + _report(buttons=1 << 7))
    watch.open()
    assert watch.wait(0) == "Valve controller"
    assert valve_report_input(_report(sticks=(0, 12000, 0, 0)), 0)[0]
    assert valve_report_input(_report(triggers=(0, 20000)), 0)[0]
    assert valve_report_input(_report(buttons=1), 1) == (False, 1)
    assert valve_report_input(_report(buttons=1 << 13), None) == (False, 1 << 13)


def test_unplugged_device_is_dropped_and_an_empty_watch_sleeps(tmp_path, monkeypatch):
    _evdev(tmp_path, "event7", "touch", 0x1B)
    slept = []
    watch = _watch(tmp_path, slept)
    watch.open()

    def gone(fd, n):
        raise OSError(19, "No such device")

    monkeypatch.setattr(iw.os, "read", gone)
    assert watch.wait(0) is None
    assert watch.wait(0.25) is None
    assert slept and slept[-1] > 0
