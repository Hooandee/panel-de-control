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
        "high", "fps", "rpg", "false", "medium",
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
        surface / "touchpad/vibration_enabled",
        surface / "touchpad/vibration_intensity",
    ]


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
