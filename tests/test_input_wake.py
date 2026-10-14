import struct

from display.input_wake import _ABSINFO, EV_ABS, EV_KEY, InputWake, deck_report_input

_EVENT = struct.Struct("llHHi")
ABS_X, BTN_SOUTH, BTN_TOUCH = 0x00, 0x130, 0x14A


def _device(tmp_path, name, label, ev_bits, events=()):
    dev = tmp_path / "dev"
    sysfs = tmp_path / "sys" / name / "device" / "capabilities"
    dev.mkdir(exist_ok=True)
    sysfs.mkdir(parents=True)
    (sysfs / "ev").write_text(f"{ev_bits:x}\n")
    (sysfs.parent / "name").write_text(label + "\n")
    (dev / name).write_bytes(b"".join(_EVENT.pack(0, 0, *e) for e in events))


def _deck_report(buttons=0, sticks=(0, 0, 0, 0), triggers=(0, 0), imu=0):
    report = bytearray(64)
    report[0], report[2], report[3] = 0x01, 0x09, 0x40
    report[8:16] = buttons.to_bytes(8, "little")
    struct.pack_into("<6h", report, 24, *([imu] * 6))
    struct.pack_into("<2H", report, 44, *triggers)
    struct.pack_into("<4h", report, 48, *sticks)
    return bytes(report)


def _hidraw(tmp_path, name, hid_id, reports=()):
    root = tmp_path / "hidroot"
    node = tmp_path / "hidsys" / name / "device"
    root.mkdir(exist_ok=True)
    node.mkdir(parents=True)
    (node / "uevent").write_text(f"DRIVER=hid-steam\nHID_ID=0003:{hid_id}\n")
    (root / name).write_bytes(b"".join(reports))


def _watch(tmp_path, axis=(0, -32768, 32767)):
    def ioctl(fd, request, buf):
        return _ABSINFO.pack(*axis, 0, 0, 0)

    return InputWake(str(tmp_path / "dev"), str(tmp_path / "sys"), str(tmp_path / "hidsys"),
                     str(tmp_path / "hidroot"), ioctl=ioctl, sleep=lambda s: None)


def test_touch_press_is_user_input(tmp_path):
    _device(tmp_path, "event7", "FTS3528:00 2808:1015", 0x1B, [(EV_KEY, BTN_TOUCH, 1)])
    watch = _watch(tmp_path)
    assert watch.open() == 1
    assert watch.wait(0) == "FTS3528:00 2808:1015"


def test_button_release_alone_is_not_input(tmp_path):
    _device(tmp_path, "event2", "Legion Go S", 0x20000B, [(EV_KEY, BTN_SOUTH, 0)])
    watch = _watch(tmp_path)
    watch.open()
    assert watch.wait(0) is None


def test_stick_drift_is_ignored_but_a_real_push_counts(tmp_path):
    _device(tmp_path, "event2", "Legion Go S", 0x20000B, [(EV_ABS, ABS_X, 2000)])
    _device(tmp_path, "event3", "Generic X-Box pad", 0x20000B, [(EV_ABS, ABS_X, 20000)])
    watch = _watch(tmp_path)
    watch.open()
    assert watch.wait(0) == "Generic X-Box pad"


def test_switches_and_keyless_sensors_are_not_watched(tmp_path):
    _device(tmp_path, "event1", "Lid Switch", 0x21, [(EV_KEY, 0, 1)])
    _device(tmp_path, "event5", "Legion Go S UNKNOWN", 0x9, [(EV_ABS, ABS_X, 30000)])
    watch = _watch(tmp_path)
    assert watch.open() == 0
    assert watch.wait(0) is None


def test_close_releases_devices(tmp_path):
    _device(tmp_path, "event7", "touch", 0x1B, [(EV_KEY, BTN_TOUCH, 1)])
    watch = _watch(tmp_path)
    watch.open()
    watch.close()
    assert watch.wait(0) is None


def test_deck_controller_button_press_is_input(tmp_path):
    _hidraw(tmp_path, "hidraw2", "000028DE:00001205",
            [_deck_report(imu=900), _deck_report(buttons=1 << 7, imu=-300)])
    watch = _watch(tmp_path)
    assert watch.open() == 1
    assert watch.wait(0) == "Valve controller"


def test_legion_go_s_valve_protocol_controller_is_read(tmp_path):
    _hidraw(tmp_path, "hidraw7", "000028DE:000012FF", [_deck_report(sticks=(0, 12000, 0, 0))])
    watch = _watch(tmp_path)
    assert watch.open() == 1
    assert watch.wait(0) == "Valve controller"


def test_deck_controller_at_rest_is_not_input(tmp_path):
    _hidraw(tmp_path, "hidraw2", "000028DE:00001205",
            [_deck_report(imu=v, sticks=(800, -900, 300, 0)) for v in (100, -2000, 3000)])
    _hidraw(tmp_path, "hidraw1", "00002808:00001015", [_deck_report(buttons=1)])
    watch = _watch(tmp_path)
    assert watch.open() == 1
    assert watch.wait(0) is None


def test_deck_report_rules():
    assert deck_report_input(_deck_report(sticks=(9000, 0, 0, 0)), 0)[0]
    assert deck_report_input(_deck_report(triggers=(0, 20000)), 0)[0]
    held = 1 << 7
    assert deck_report_input(_deck_report(buttons=held), held) == (False, held)
    assert deck_report_input(b"\x01\x00\x01" + bytes(61), 0) == (False, 0)


def test_unplugged_device_is_dropped_instead_of_spinning(tmp_path, monkeypatch):
    _device(tmp_path, "event7", "touch", 0x1B)
    watch = _watch(tmp_path)
    assert watch.open() == 1
    import display.input_wake as iw

    def gone(fd, n):
        raise OSError(19, "No such device")

    monkeypatch.setattr(iw.os, "read", gone)
    assert watch.wait(0) is None
    assert watch._fds == {}


def test_waiting_with_no_devices_sleeps_instead_of_returning_at_once(tmp_path):
    slept = []
    watch = InputWake(str(tmp_path / "none"), str(tmp_path / "none"), str(tmp_path / "none"),
                      str(tmp_path / "none"), sleep=slept.append)
    assert watch.open() == 0
    assert watch.wait(0.25) is None
    assert slept and slept[0] > 0
