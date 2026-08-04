from pathlib import Path

import pytest


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _write_bytes(path: Path, value: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _xbox_hid_descriptor() -> bytes:
    return bytes([
        0x05, 0x0F,       # Usage Page (Physical Interface)
        0x09, 0x02,       # Usage (Physical Input Device)
        0xA1, 0x01,       # Collection (Application)
        0x85, 0x0D,       # Report ID 0x0d
        0x91, 0x02,       # Output report
        0xC0,
    ])


def _surface(tmp_path: Path, hidraw: str = "hidraw3") -> tuple[Path, Path]:
    intensity = (
        tmp_path / "sys/bus/hid/drivers/asus_rog_ally"
        / "0003:0B05:1B4C.0007/vibration_intensity"
    )
    _write_text(intensity, "100 100\n")
    device = tmp_path / f"sys/class/hidraw/{hidraw}/device"
    _write_text(
        device / "uevent",
        "HID_ID=0003:00000B05:00001B4C\n",
    )
    _write_bytes(device / "report_descriptor", _xbox_hid_descriptor())
    raw = tmp_path / f"dev/{hidraw}"
    _write_bytes(raw)
    return intensity, raw


def test_report_builder_addresses_each_xbox_motor_independently():
    from controllers.asus_xbox_haptics import build_rumble_report

    assert build_rumble_report("trigger_left", 50) == bytes([
        0x0D, 0x01, 50, 0, 0, 0, 0xFF, 0, 0xEB,
    ])
    assert build_rumble_report("trigger_right", 25) == bytes([
        0x0D, 0x02, 0, 25, 0, 0, 0xFF, 0, 0xEB,
    ])
    assert build_rumble_report("strong", 75) == bytes([
        0x0D, 0x04, 0, 0, 75, 0, 0xFF, 0, 0xEB,
    ])
    assert build_rumble_report("weak", 100) == bytes([
        0x0D, 0x08, 0, 0, 0, 100, 0xFF, 0, 0xEB,
    ])
    assert build_rumble_report("all", 40) == bytes([
        0x0D, 0x0F, 40, 40, 40, 40, 0xFF, 0, 0xEB,
    ])


def test_xbox_ally_x_surface_requires_exact_device_and_unique_interfaces(
    tmp_path,
):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _surface(tmp_path)
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path)
    )

    assert adapter.state() == {
        "mode": "asus_xbox_hd",
        "persistent": True,
        "left": 100,
        "right": 100,
        "min": 0,
        "max": 100,
        "step": 5,
        "readback": True,
        "connected": True,
        "hd_game_supported": False,
    }
    assert adapter.capabilities() == {
        "mode": "asus_xbox_hd",
        "channels": ["left", "right"],
        "readback": "driver",
        "min": 0,
        "max": 100,
        "step": 5,
        "hd_game_supported": False,
        "trigger_source_options": ["off", "strong", "weak", "mix"],
        "test": {
            "patterns": ["pulse"],
            "channels": [
                "trigger_left", "trigger_right", "strong", "weak", "all",
            ],
        },
    }

    wrong = AsusXboxHapticsAdapter("rog_ally_x", root=str(tmp_path))
    assert wrong.state() is None
    assert wrong.capabilities() is None


def test_xbox_ally_x_rejects_ambiguous_hidraw_surface(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _surface(tmp_path, "hidraw3")
    _surface(tmp_path, "hidraw4")
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path)
    )

    assert adapter.state()["mode"] == "asus_xbox_hd"
    assert adapter.capabilities()["test"] == {
        "patterns": [],
        "channels": [],
    }
    assert adapter.test("pulse", "trigger_left", 50)["reason"] == (
        "unsupported_channel"
    )


def test_xbox_ally_x_persistent_gain_requires_exact_readback(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    intensity, _raw = _surface(tmp_path)
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path)
    )

    assert adapter.capture_baseline() == {
        "native_left": 64,
        "native_right": 64,
    }
    assert adapter.apply({"left": 35, "right": 80}) is True
    assert intensity.read_text() == "22 51\n"
    assert adapter.restore_baseline({
        "native_left": 64,
        "native_right": 64,
    }) is True
    assert intensity.read_text() == "64 64\n"


def test_xbox_ally_x_rejects_non_finite_calibration_without_raising(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _surface(tmp_path)
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path)
    )

    assert adapter.apply({"left": float("nan"), "right": 50}) is False
    assert adapter.apply({"left": 50, "right": float("inf")}) is False
    assert adapter.diagnostics()["reason"] == "invalid_value"


def test_xbox_ally_x_test_always_sends_explicit_stop(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _intensity, raw = _surface(tmp_path)
    reports = []

    def write_report(path, report):
        assert path == str(raw)
        reports.append(bytes(report))
        return len(report)

    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x",
        root=str(tmp_path),
        write_report=write_report,
        sleep=lambda _seconds: None,
    )

    assert adapter.test("pulse", "trigger_left", 50) == {
        "sent": True,
        "stopped": True,
        "restored": True,
        "reason": None,
    }
    assert reports == [
        bytes([0x0D, 0x01, 50, 0, 0, 0, 0xFF, 0, 0xEB]),
        bytes([0x0D, 0x0F, 0, 0, 0, 0, 0xFF, 0, 0xEB]),
    ]


@pytest.mark.parametrize(
    ("gain", "source"),
    [(0, "strong"), (70, "off")],
)
def test_xbox_ally_x_disabled_trigger_test_only_sends_stop(
    tmp_path, gain, source,
):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _intensity, raw = _surface(tmp_path)
    reports = []

    class Dbus:
        def xbox_hd_haptics(self):
            return {
                "enabled": True,
                "trigger_left": gain,
                "trigger_right": 50,
                "trigger_left_source": source,
                "trigger_right_source": "weak",
            }

    def write_report(path, report):
        assert path == str(raw)
        reports.append(bytes(report))
        return len(report)

    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x",
        root=str(tmp_path),
        write_report=write_report,
        sleep=lambda _seconds: None,
        dbus=Dbus(),
    )

    assert adapter.test("pulse", "trigger_left", 50) == {
        "sent": False,
        "stopped": True,
        "restored": True,
        "reason": "motor_disabled",
    }
    assert reports == [
        bytes([0x0D, 0x0F, 0, 0, 0, 0, 0xFF, 0, 0xEB]),
    ]


def test_xbox_ally_x_merges_persistent_game_hd_haptics(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _surface(tmp_path)

    class Dbus:
        applied = None

        def xbox_hd_haptics(self):
            return {
                "enabled": True,
                "trigger_left": 70,
                "trigger_right": 40,
                "trigger_left_source": "strong",
                "trigger_right_source": "weak",
            }

        def set_xbox_hd_haptics(self, config):
            self.applied = dict(config)
            return True

    dbus = Dbus()
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path), dbus=dbus,
    )

    state = adapter.state()
    assert state["hd_game_supported"] is True
    assert state["trigger_left"] == 70
    assert state["trigger_left_source"] == "strong"
    assert adapter.apply({
        "left": 35,
        "right": 45,
        "hd_game_enabled": True,
        "trigger_left": 60,
        "trigger_right": 50,
        "trigger_left_source": "mix",
        "trigger_right_source": "weak",
    }) is True
    assert dbus.applied == {
        "enabled": True,
        "trigger_left": 60,
        "trigger_right": 50,
        "trigger_left_source": "mix",
        "trigger_right_source": "weak",
    }


def test_xbox_ally_x_capabilities_reuse_the_captured_state(tmp_path):
    from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter

    _surface(tmp_path)

    class Dbus:
        calls = 0

        def xbox_hd_haptics(self):
            self.calls += 1
            if self.calls > 1:
                return None
            return {
                "enabled": True,
                "trigger_left": 70,
                "trigger_right": 40,
                "trigger_left_source": "strong",
                "trigger_right_source": "weak",
            }

    dbus = Dbus()
    adapter = AsusXboxHapticsAdapter(
        "rog_xbox_ally_x", root=str(tmp_path), dbus=dbus,
    )

    state = adapter.state()
    capabilities = adapter.capabilities(state)

    assert capabilities["hd_game_supported"] is True
    assert dbus.calls == 1
