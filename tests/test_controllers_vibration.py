import struct


class FakeDbus:
    def __init__(self, paths=()):
        self._paths = list(paths)

    def source_device_paths(self):
        return list(self._paths)


def _write(path, value=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _controller(*args, **kwargs):
    from controllers.vibration import VibrationController

    return VibrationController(*args, **kwargs)


def test_asus_dual_motor_intensity_writes_and_reads_both_motors(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "64 51\n")
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    assert controller.state() == {
        "mode": "dual",
        "persistent": True,
        "left": 100,
        "right": 80,
        "min": 0,
        "max": 100,
        "step": 5,
        "readback": True,
    }
    assert controller.apply({"left": 35, "right": 45}) is True
    assert intensity.read_text() == "22 29\n"
    assert controller.state()["left"] == 35
    assert controller.state()["right"] == 45


def test_asus_legacy_full_scale_readback_is_normalized_before_writing(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "100 100\n")
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    assert controller.state()["left"] == 100
    assert controller.state()["right"] == 100


def test_asus_external_baseline_round_trips_exact_native_values(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "1 63\n")
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    baseline = controller.capture_baseline()
    assert baseline == {"native_left": 1, "native_right": 63}
    assert controller.apply({"left": 35, "right": 45}) is True
    assert controller.restore_baseline(baseline) is True
    assert intensity.read_text() == "1 63\n"
    assert controller.apply({"left": 20, "right": 100}) is True
    assert intensity.read_text() == "13 64\n"
    assert controller.state()["left"] == 20
    assert controller.state()["right"] == 100


def test_asus_dual_motor_rolls_back_when_readback_mismatches(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "58 45\n")

    def mismatching_write(_path, value):
        intensity.write_text("10 10\n" if value == "16 19\n" else value)

    controller = _controller(
        "rog_ally", FakeDbus(), root=str(tmp_path), write_text=mismatching_write
    )

    assert controller.apply({"left": 25, "right": 30}) is False
    assert intensity.read_text() == "58 45\n"


def test_legion_gain_uses_the_single_force_feedback_source(tmp_path):
    capabilities = (
        tmp_path / "sys/class/input/event2/device/capabilities/ff"
    )
    _write(capabilities, "107030000 0\n")
    device = tmp_path / "dev/input/event2"
    _write(device)
    controller = _controller(
        "legion_go",
        FakeDbus(("/dev/input/event2", "/dev/input/event3")),
        root=str(tmp_path),
    )

    state = controller.state()
    assert state == {
        "mode": "gain",
        "persistent": True,
        "value": None,
        "min": 0,
        "max": 100,
        "step": 5,
        "readback": False,
    }
    assert controller.apply({"value": 65}) is True

    _sec, _usec, event_type, event_code, value = struct.unpack(
        "llHHi", device.read_bytes()
    )
    assert (event_type, event_code) == (0x15, 0x60)
    assert value == round(65 * 0xFFFF / 100)


def test_gain_refuses_ambiguous_force_feedback_sources(tmp_path):
    for event in ("event2", "event3"):
        _write(
            tmp_path / f"sys/class/input/{event}/device/capabilities/ff",
            "107030000 0\n",
        )
        _write(tmp_path / f"dev/input/{event}")

    controller = _controller(
        "legion_go",
        FakeDbus(("/dev/input/event2", "/dev/input/event3")),
        root=str(tmp_path),
    )

    assert controller.state() is None
    assert controller.apply({"value": 50}) is False


def test_gain_is_not_inferred_for_non_legion_device(tmp_path):
    _write(
        tmp_path / "sys/class/input/event2/device/capabilities/ff",
        "107030000 0\n",
    )
    _write(tmp_path / "dev/input/event2")
    controller = _controller(
        "msi_claw_8_ai_plus",
        FakeDbus(("/dev/input/event2",)),
        root=str(tmp_path),
    )

    assert controller.state() is None
    assert controller.apply({"value": 50}) is False


def test_asus_failed_apply_reports_confirmed_rollback(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "58 45\n")

    def mismatching_write(_path, value):
        intensity.write_text("10 10\n" if value == "16 19\n" else value)

    controller = _controller(
        "rog_ally", FakeDbus(), root=str(tmp_path),
        write_text=mismatching_write,
    )

    assert controller.apply({"left": 25, "right": 30}) is False
    assert controller.diagnostics()["rollback_confirmed"] is True
