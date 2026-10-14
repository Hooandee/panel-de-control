import struct

from display.input_wake import _ABSINFO, EV_ABS, EV_KEY, InputWake

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


def _watch(tmp_path, axis=(0, -32768, 32767)):
    def ioctl(fd, request, buf):
        return _ABSINFO.pack(*axis, 0, 0, 0)

    return InputWake(str(tmp_path / "dev"), str(tmp_path / "sys"), ioctl=ioctl)


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
