from controllers.lenovo_go_vibration import LenovoGoVibrationAdapter


INTENSITIES = "off low medium high\n"
PATTERNS = "fps racing standard spg rpg\n"
BOOLEANS = "true false\n"


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _surface(tmp_path, name="controller0"):
    root = tmp_path / name
    _write(root / "rumble_intensity", "medium\n")
    _write(root / "rumble_intensity_index", INTENSITIES)
    for handle in ("left_handle", "right_handle"):
        _write(root / handle / "rumble_mode", "standard\n")
        _write(root / handle / "rumble_mode_index", PATTERNS)
    _write(root / "touchpad/vibration_enabled", "true\n")
    _write(root / "touchpad/vibration_enabled_index", BOOLEANS)
    _write(root / "touchpad/vibration_intensity", "low\n")
    _write(root / "touchpad/vibration_intensity_index", INTENSITIES)
    return root


def _unknown_surface(tmp_path, name="controller0"):
    root = _surface(tmp_path, name)
    _write(root / "rumble_intensity", "unknown\n")
    _write(root / "left_handle/rumble_mode", "unknown\n")
    _write(root / "right_handle/rumble_mode", "unknown\n")
    _write(root / "touchpad/vibration_enabled", "unknown\n")
    _write(root / "touchpad/vibration_intensity", "unknown\n")
    return root


def _adapter(tmp_path, roots, **kwargs):
    kwargs.setdefault("sleep", lambda _seconds: None)
    return LenovoGoVibrationAdapter(
        "legion_go_2",
        source_paths=lambda: ["/dev/input/event2"],
        root=str(tmp_path),
        candidate_roots=lambda: [str(path) for path in roots],
        **kwargs,
    )


def test_complete_surface_reports_actual_state_and_live_legal_options(tmp_path):
    surface = _surface(tmp_path)
    adapter = _adapter(tmp_path, [surface])

    assert adapter.state() == {
        "intensity": "medium",
        "left_pattern": "standard",
        "right_pattern": "standard",
        "touchpad_enabled": True,
        "touchpad_intensity": "low",
    }
    assert adapter.capabilities() == {
        "intensity_options": ["off", "low", "medium", "high"],
        "left_pattern_options": ["fps", "racing", "standard", "spg", "rpg"],
        "right_pattern_options": ["fps", "racing", "standard", "spg", "rpg"],
        "touchpad_enabled_options": [True, False],
        "touchpad_intensity_options": ["off", "low", "medium", "high"],
        "readback": "driver",
    }


def test_unknown_readback_keeps_surface_available_without_inventing_state(
    tmp_path,
):
    adapter = _adapter(tmp_path, [_unknown_surface(tmp_path)])

    assert adapter.state() is None
    assert adapter.capabilities() == {
        "intensity_options": ["off", "low", "medium", "high"],
        "left_pattern_options": ["fps", "racing", "standard", "spg", "rpg"],
        "right_pattern_options": ["fps", "racing", "standard", "spg", "rpg"],
        "touchpad_enabled_options": [True, False],
        "touchpad_intensity_options": ["off", "low", "medium", "high"],
        "readback": "none",
    }


def test_unrecognized_readback_is_not_treated_as_driver_unknown(tmp_path):
    surface = _unknown_surface(tmp_path)
    _write(surface / "rumble_intensity", "corrupt\n")
    adapter = _adapter(tmp_path, [surface])

    assert adapter.capabilities() is None
    assert adapter.diagnostics()["probe"]["reason"] == "invalid_readback"


def test_mixed_known_and_unknown_readback_is_not_safe_to_write(tmp_path):
    surface = _unknown_surface(tmp_path)
    _write(surface / "rumble_intensity", "medium\n")
    adapter = _adapter(tmp_path, [surface])

    assert adapter.capabilities() is None
    assert adapter.diagnostics()["probe"]["reason"] == "mixed_readback"


def test_unknown_readback_accepts_a_complete_profile_without_fake_confirmation(
    tmp_path,
):
    surface = _unknown_surface(tmp_path)
    writes = []

    def accept_without_readback(path, value):
        writes.append((path, value))

    adapter = _adapter(
        tmp_path, [surface], write_text=accept_without_readback
    )
    desired = {
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }

    assert adapter.apply(desired) is True
    assert [value for _, value in writes] == [
        "high", "fps", "rpg", "medium", "false",
    ]
    assert adapter.diagnostics() == {
        "probe": {
            "available": True,
            "reason": "available_without_readback",
            "candidate_count": 1,
            "candidates": [surface.name],
        },
        "mode": "lenovo_hd",
        "ok": True,
        "readback": False,
        "confirmation": "accepted",
    }


def test_unknown_readback_partial_failure_cannot_claim_rollback(tmp_path):
    surface = _unknown_surface(tmp_path)

    def fail_right(path, _value):
        if path == surface / "right_handle/rumble_mode":
            raise OSError("right handle unavailable")

    adapter = _adapter(tmp_path, [surface], write_text=fail_right)

    assert adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }) is False
    assert adapter.diagnostics()["rollback_confirmed"] is False


def test_known_readback_mismatch_fails_and_restores_the_surface(
    tmp_path,
):
    surface = _surface(tmp_path)

    def accept_without_changing_readback(_path, _value):
        pass

    adapter = _adapter(
        tmp_path, [surface], write_text=accept_without_changing_readback
    )

    assert adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }) is False
    assert adapter.state() == {
        "intensity": "medium",
        "left_pattern": "standard",
        "right_pattern": "standard",
        "touchpad_enabled": True,
        "touchpad_intensity": "low",
    }
    assert adapter.capabilities()["readback"] == "driver"
    assert adapter.diagnostics()["reason"] == "readback_mismatch"
    assert adapter.diagnostics()["rollback_confirmed"] is True


def test_surface_is_never_selected_for_other_legion_models(tmp_path):
    surface = _surface(tmp_path)
    for device_key in ("legion_go", "legion_go_s", "generic"):
        adapter = LenovoGoVibrationAdapter(
            device_key,
            source_paths=lambda: ["/dev/input/event2"],
            root=str(tmp_path),
            candidate_roots=lambda: [str(surface)],
        )
        assert adapter.state() is None


def test_partial_or_ambiguous_surface_is_rejected(tmp_path):
    first = _surface(tmp_path, "first")
    second = _surface(tmp_path, "second")
    (first / "touchpad/vibration_intensity_index").unlink()

    assert _adapter(tmp_path, [first]).state() is None
    assert _adapter(tmp_path, [second, _surface(tmp_path, "third")]).state() is None


def test_apply_writes_each_handle_pattern_and_confirms_readback(
    tmp_path,
):
    surface = _surface(tmp_path)
    writes = []

    def write(path, value):
        writes.append((path, value))
        path.write_text(value)

    adapter = _adapter(tmp_path, [surface], write_text=write)
    result = adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    })

    assert result is True
    assert (surface / "left_handle/rumble_mode").read_text() == "fps"
    assert (surface / "right_handle/rumble_mode").read_text() == "rpg"
    assert adapter.state() == {
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }
    assert [path for path, _ in writes] == [
        surface / "rumble_intensity",
        surface / "left_handle/rumble_mode",
        surface / "right_handle/rumble_mode",
        surface / "touchpad/vibration_intensity",
        surface / "touchpad/vibration_enabled",
    ]


def test_apply_skips_every_unchanged_driver_attribute(tmp_path):
    surface = _surface(tmp_path)
    writes = []
    adapter = _adapter(
        tmp_path, [surface],
        write_text=lambda path, value: writes.append((path, value)),
    )

    assert adapter.apply({
        "intensity": "medium",
        "left_pattern": "standard",
        "right_pattern": "standard",
        "touchpad_enabled": True,
        "touchpad_intensity": "low",
    }) is True
    assert writes == []


def test_apply_left_pattern_does_not_touch_other_motors_or_touchpad(tmp_path):
    surface = _surface(tmp_path)
    writes = []

    def write(path, value):
        writes.append((path, value))
        path.write_text(value)

    adapter = _adapter(tmp_path, [surface], write_text=write)

    assert adapter.apply({"left_pattern": "racing"}) is True
    assert writes == [(surface / "left_handle/rumble_mode", "racing")]


def test_touchpad_intensity_reasserts_enabled_after_driver_side_effect(tmp_path):
    surface = _surface(tmp_path)
    enabled = surface / "touchpad/vibration_enabled"
    intensity = surface / "touchpad/vibration_intensity"
    writes = []

    def firmware_write(path, value):
        writes.append((path, value))
        path.write_text(value)
        if path == intensity:
            enabled.write_text("true")

    adapter = _adapter(tmp_path, [surface], write_text=firmware_write)
    enabled.write_text("false")

    assert adapter.apply({"touchpad_intensity": "high"}) is True
    assert writes == [(intensity, "high"), (enabled, "false")]
    assert enabled.read_text() == "false"


def test_apply_waits_for_delayed_driver_readback(tmp_path):
    surface = _surface(tmp_path)
    pending = {}

    def delayed_write(path, value):
        pending[path] = [value, 2]

    def advance(_seconds):
        for path, item in list(pending.items()):
            item[1] -= 1
            if item[1] == 0:
                path.write_text(item[0])
                pending.pop(path)

    adapter = _adapter(
        tmp_path, [surface], write_text=delayed_write, sleep=advance,
    )
    desired = {
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }

    assert adapter.apply(desired) is True
    assert adapter.state() == desired
    assert adapter.diagnostics()["confirmation"] == "driver"


def test_partial_write_rolls_back_every_changed_attribute(tmp_path):
    surface = _surface(tmp_path)

    def fail_right(path, value):
        if path == surface / "right_handle/rumble_mode" and value == "rpg":
            raise OSError("right handle unavailable")
        path.write_text(value)

    adapter = _adapter(tmp_path, [surface], write_text=fail_right)

    assert adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }) is False
    assert adapter.state() == {
        "intensity": "medium",
        "left_pattern": "standard",
        "right_pattern": "standard",
        "touchpad_enabled": True,
        "touchpad_intensity": "low",
    }
    diagnostics = adapter.diagnostics()
    assert diagnostics["probe"]["available"] is True
    assert {key: diagnostics[key] for key in (
        "mode", "ok", "reason", "rollback_confirmed",
    )} == {
        "mode": "lenovo_hd",
        "ok": False,
        "reason": "write_failed",
        "rollback_confirmed": True,
    }


def test_rollback_restores_touchpad_enabled_after_intensity(tmp_path):
    surface = _surface(tmp_path)
    enabled = surface / "touchpad/vibration_enabled"
    intensity = surface / "touchpad/vibration_intensity"
    enabled.write_text("false")
    intensity.write_text("off")
    writes = []
    enabled_writes = 0

    def firmware_write(path, value):
        nonlocal enabled_writes
        writes.append((path, value))
        if path == intensity:
            path.write_text(value)
            enabled.write_text("true")
        elif path == enabled:
            enabled_writes += 1
            if enabled_writes > 1:
                path.write_text(value)
        else:
            path.write_text(value)

    adapter = _adapter(tmp_path, [surface], write_text=firmware_write)

    assert adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "high",
    }) is False
    assert enabled.read_text() == "false"
    assert intensity.read_text() == "off"
    assert [path for path, _ in writes[-2:]] == [intensity, enabled]
    assert adapter.diagnostics()["rollback_confirmed"] is True


def test_intensity_mismatch_rolls_back_the_coupled_touchpad_pair(tmp_path):
    surface = _surface(tmp_path)
    enabled = surface / "touchpad/vibration_enabled"
    intensity = surface / "touchpad/vibration_intensity"
    enabled.write_text("false")
    intensity.write_text("off")
    writes = []

    def firmware_write(path, value):
        writes.append((path, value))
        if path == intensity and value == "high":
            enabled.write_text("true")
        elif path == intensity:
            path.write_text(value)
            enabled.write_text("true")
        else:
            path.write_text(value)

    adapter = _adapter(tmp_path, [surface], write_text=firmware_write)

    assert adapter.apply({
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "rpg",
        "touchpad_enabled": False,
        "touchpad_intensity": "high",
    }) is False
    assert enabled.read_text() == "false"
    assert intensity.read_text() == "off"
    assert [path for path, _ in writes[-2:]] == [intensity, enabled]
    assert adapter.diagnostics()["rollback_confirmed"] is True


def test_diagnostics_explain_partial_and_ambiguous_surfaces(tmp_path):
    partial = _surface(tmp_path, "partial")
    (partial / "touchpad/vibration_intensity_index").unlink()
    adapter = _adapter(tmp_path, [partial])
    assert adapter.state() is None
    assert adapter.diagnostics()["probe"]["reason"] == "incomplete_surface"

    adapter = _adapter(
        tmp_path,
        [_surface(tmp_path, "first"), _surface(tmp_path, "second")],
    )
    assert adapter.state() is None
    assert adapter.diagnostics()["probe"]["reason"] == "ambiguous"
    assert adapter.diagnostics()["probe"]["candidate_count"] == 2


def test_default_discovery_requires_source_usb_and_official_go_2_pid(tmp_path):
    usb = tmp_path / "sys/devices/pci0000:00/usb1/1-2"
    _write(usb / "idVendor", "17ef\n")
    _write(usb / "idProduct", "61eb\n")
    hid = usb / "1-2:1.0/0003:17EF:61EB.0001"
    _surface(hid.parent, hid.name)
    input_device = hid / "input/input2"
    input_device.mkdir(parents=True)

    driver = tmp_path / "sys/bus/hid/drivers/hid-lenovo-go"
    driver.mkdir(parents=True)
    (driver / hid.name).symlink_to(hid, target_is_directory=True)
    event = tmp_path / "sys/class/input/event2"
    event.mkdir(parents=True)
    (event / "device").symlink_to(input_device, target_is_directory=True)

    adapter = LenovoGoVibrationAdapter(
        "legion_go_2",
        source_paths=lambda: ["/dev/input/event2"],
        root=str(tmp_path),
    )
    assert adapter.state()["left_pattern"] == "standard"

    (usb / "idProduct").write_text("6184\n")
    assert adapter.state() is None


def test_asymmetric_driver_state_is_supported_and_preserved(tmp_path):
    surface = _surface(tmp_path)
    (surface / "right_handle/rumble_mode").write_text("rpg\n")
    adapter = _adapter(tmp_path, [surface])

    assert adapter.state()["left_pattern"] == "standard"
    assert adapter.state()["right_pattern"] == "rpg"
