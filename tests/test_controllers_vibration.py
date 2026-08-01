import struct


class FakeDbus:
    def __init__(self, paths=(), enabled=True, rumble=True, stop=True):
        self._paths = list(paths)
        self._enabled = enabled
        self._rumble = rumble
        self._stop = stop
        self.rumbles = []
        self.stop_calls = 0

    def source_device_paths(self):
        return list(self._paths)

    def force_feedback_enabled(self):
        return self._enabled

    def rumble(self, strength):
        self.rumbles.append(strength)
        return self._rumble

    def stop_rumble(self):
        self.stop_calls += 1
        return self._stop


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


def test_asus_capabilities_distinguish_driver_readback_and_test_channels(
    tmp_path,
):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "64 51\n")
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    assert controller.capabilities() == {
        "mode": "dual",
        "channels": ["left", "right"],
        "readback": "driver",
        "min": 0,
        "max": 100,
        "step": 5,
        "test": {
            "patterns": ["pulse"],
            "channels": ["left", "right", "both"],
        },
    }


def test_asus_rejects_values_outside_the_official_native_range(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "100 100\n")
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    assert controller.state() is None
    assert controller.capture_baseline() == {}


def test_asus_native_motor_range_is_not_inherited_by_other_skus(tmp_path):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "64 51\n")

    for device_key in (
        "rog_ally_x", "rog_xbox_ally", "rog_xbox_ally_x",
    ):
        controller = _controller(
            device_key, FakeDbus(), root=str(tmp_path)
        )
        assert controller.state() is None
        assert controller.capabilities()["mode"] == "enabled_only"


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

    assert controller.capabilities() == {
        "mode": "gain",
        "channels": [],
        "readback": "none",
        "min": 0,
        "max": 100,
        "step": 5,
        "test": {
            "patterns": ["pulse"],
            "channels": ["strong", "weak", "both"],
        },
    }


def test_legion_direct_channel_test_uses_exact_strong_and_weak_magnitudes(
    tmp_path,
):
    from controllers import vibration as vib

    capabilities = (
        tmp_path / "sys/class/input/event2/device/capabilities/ff"
    )
    _write(capabilities, "107030000 0\n")
    device = tmp_path / "dev/input/event2"
    _write(device)
    ioctls = []
    writes = []
    uploaded = []

    def ioctl(_fd, request, argument, mutate=False):
        ioctls.append((request, mutate))
        if request == vib._EVIOCSFF:
            effect = vib._FFEffect.from_buffer(argument)
            uploaded.append((
                effect.u.rumble.strong_magnitude,
                effect.u.rumble.weak_magnitude,
            ))
            effect.id = 7
        return 0

    controller = _controller(
        "legion_go",
        FakeDbus(("/dev/input/event2",)),
        root=str(tmp_path),
        open_device=lambda _path, _flags: 12,
        write_event=lambda _fd, event: writes.append(event) or len(event),
        ioctl=ioctl,
        close_device=lambda _fd: None,
        sleep=lambda _seconds: None,
    )

    results = [
        controller.test("pulse", channel, 50)
        for channel in ("strong", "weak", "both")
    ]

    magnitude = round(0xFFFF * 0.5)
    assert uploaded == [
        (magnitude, 0), (0, magnitude), (magnitude, magnitude),
    ]
    assert len(writes) == 6
    assert [struct.unpack("llHHi", event)[-1] for event in writes] == [
        1, 0, 1, 0, 1, 0,
    ]
    assert ioctls == [
        (request, mutate)
        for _ in range(3)
        for request, mutate in (
            (vib._EVIOCSFF, True), (vib._EVIOCRMFF, False),
        )
    ]
    assert results == [{
        "sent": True,
        "stopped": True,
        "restored": True,
        "reason": None,
    }] * 3


def test_legion_direct_test_reports_stop_and_erase_failures(tmp_path):
    from controllers import vibration as vib

    capabilities = (
        tmp_path / "sys/class/input/event2/device/capabilities/ff"
    )
    _write(capabilities, "107030000 0\n")
    _write(tmp_path / "dev/input/event2")

    def run(*, short_stop=False, erase_fails=False):
        write_count = 0

        def ioctl(_fd, request, argument, mutate=False):
            if request == vib._EVIOCSFF:
                vib._FFEffect.from_buffer(argument).id = 3
            elif erase_fails:
                raise OSError("erase failed")
            return 0

        def write_event(_fd, event):
            nonlocal write_count
            write_count += 1
            return len(event) - (1 if short_stop and write_count == 2 else 0)

        controller = _controller(
            "legion_go",
            FakeDbus(("/dev/input/event2",)),
            root=str(tmp_path),
            open_device=lambda _path, _flags: 12,
            write_event=write_event,
            ioctl=ioctl,
            close_device=lambda _fd: None,
            sleep=lambda _seconds: None,
        )
        return controller.test("pulse", "strong", 50)

    assert run(short_stop=True) == {
        "sent": True,
        "stopped": False,
        "restored": True,
        "reason": "stop_failed",
    }
    assert run(erase_fails=True) == {
        "sent": True,
        "stopped": True,
        "restored": False,
        "reason": "restore_failed",
    }


def test_failed_transient_start_still_attempts_stop(tmp_path):
    dbus = FakeDbus(rumble=False)
    controller = _controller(
        "msi_claw_8_ai_plus", dbus, root=str(tmp_path)
    )

    assert controller.test("pulse", "both", 40) == {
        "sent": False,
        "stopped": True,
        "restored": True,
        "reason": "start_failed",
    }
    assert dbus.stop_calls == 1


def test_asus_left_test_restores_exact_raw_pair(tmp_path, monkeypatch):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "13 51\n")
    writes = []

    def write(_path, value):
        writes.append(value)
        intensity.write_text(value)

    monkeypatch.setattr("controllers.vibration.time.sleep", lambda _: None)
    dbus = FakeDbus()
    controller = _controller(
        "rog_ally", dbus, root=str(tmp_path), write_text=write
    )

    assert controller.test("pulse", "left", 50) == {
        "sent": True,
        "stopped": True,
        "restored": True,
        "reason": None,
    }
    assert writes == ["32 0\n", "13 51\n"]
    assert dbus.rumbles == [1.0]
    assert intensity.read_text() == "13 51\n"


def test_asus_test_restores_even_when_stop_is_not_confirmed(
    tmp_path, monkeypatch,
):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "7 43\n")
    monkeypatch.setattr("controllers.vibration.time.sleep", lambda _: None)
    dbus = FakeDbus(stop=False)
    controller = _controller("rog_ally", dbus, root=str(tmp_path))

    assert controller.test("pulse", "right", 25) == {
        "sent": True,
        "stopped": False,
        "restored": True,
        "reason": "stop_failed",
    }
    assert intensity.read_text() == "7 43\n"


def test_asus_test_reports_unconfirmed_restore(tmp_path, monkeypatch):
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1ABE.0003/vibration_intensity"
    )
    _write(intensity, "13 51\n")

    def ignore_restore(_path, value):
        if value != "13 51\n":
            intensity.write_text(value)

    monkeypatch.setattr("controllers.vibration.time.sleep", lambda _: None)
    controller = _controller(
        "rog_ally", FakeDbus(), root=str(tmp_path),
        write_text=ignore_restore,
    )

    assert controller.test("pulse", "left", 50) == {
        "sent": True,
        "stopped": True,
        "restored": False,
        "reason": "restore_failed",
    }


def test_asus_refuses_ambiguous_native_nodes(tmp_path):
    for device in ("0003:0B05:1ABE.0003", "0003:0B05:1ABE.0004"):
        _write(
            tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
            / device / "vibration_intensity",
            "32 32\n",
        )
    controller = _controller("rog_ally", FakeDbus(), root=str(tmp_path))

    assert controller.state() is None
    assert controller.capabilities()["mode"] == "enabled_only"
    assert controller.test("pulse", "left", 50)["reason"] == (
        "unsupported_channel"
    )


def test_vibration_test_rejects_unbounded_inputs(tmp_path):
    controller = _controller(
        "msi_claw_8_ai_plus", FakeDbus(), root=str(tmp_path)
    )

    assert controller.test("loop", "both", 50)["reason"] == (
        "unsupported_pattern"
    )
    assert controller.test("pulse", "both", 101)["reason"] == (
        "invalid_strength"
    )


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
