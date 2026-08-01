from types import SimpleNamespace

from controllers.dbus import IpDbus


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_capability_probe_keeps_bounded_structured_diagnostics():
    events = []
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice7\n"),
        _result(
            'as 4 "Gamepad:Button:South" "Gamepad:Button:LeftPaddle1" '
            '"Gamepad:Button:RightPaddle1" "Gamepad:Button:QuickAccess"\n'
        ),
    ])
    dbus = IpDbus(run=lambda _args: next(responses), event_cb=events.append)

    capabilities = dbus.capabilities()

    assert capabilities == [
        "Gamepad:Button:South",
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
        "Gamepad:Button:QuickAccess",
    ]
    assert dbus.diagnostics() == {
        "composite_path_available": True,
        "capability_count": 4,
        "capabilities": sorted(capabilities),
        "last_operation": {
            "operation": "read_capabilities",
            "ok": True,
            "capability_count": 4,
        },
    }
    assert events[-1] == dbus.diagnostics()["last_operation"]


def test_capability_probe_does_not_truncate_live_behavior():
    capabilities = [
        *(f"Keyboard:Key{i}" for i in range(70)),
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
    ]
    encoded = " ".join(f'"{capability}"' for capability in capabilities)
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice7\n"),
        _result(f"as {len(capabilities)} {encoded}\n"),
    ])
    dbus = IpDbus(run=lambda _args: next(responses))

    assert dbus.capabilities() == capabilities
    diagnostics = dbus.diagnostics()
    assert diagnostics["capability_count"] == len(capabilities)
    assert len(diagnostics["capabilities"]) == 64
    assert "Gamepad:Button:LeftPaddle1" in diagnostics["capabilities"]
    assert "Gamepad:Button:RightPaddle1" in diagnostics["capabilities"]


def test_failed_operation_records_stage_without_process_output():
    events = []
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice2\n"),
        _result(returncode=1),
    ])
    dbus = IpDbus(run=lambda _args: next(responses), event_cb=events.append)

    assert dbus.reset_default() is False

    assert dbus.diagnostics()["composite_path_available"] is False
    assert dbus.diagnostics()["last_operation"] == {
        "operation": "reset_default",
        "ok": False,
        "reason": "busctl_exit",
        "returncode": 1,
    }
    assert events[-1] == dbus.diagnostics()["last_operation"]


def test_composite_invalidation_clears_stale_capabilities():
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice2\n"),
        _result('as 1 "Gamepad:Button:LeftPaddle1"\n'),
        _result(returncode=1),
    ])
    dbus = IpDbus(run=lambda _args: next(responses))
    assert dbus.capabilities() == ["Gamepad:Button:LeftPaddle1"]

    assert dbus.reset_default() is False

    assert dbus.diagnostics()["composite_path_available"] is False
    assert dbus.diagnostics()["capability_count"] == 0
    assert dbus.diagnostics()["capabilities"] == []


def test_unchanged_capability_reads_do_not_repeat_success_events():
    events = []
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice2\n"),
        _result('as 1 "Gamepad:Button:LeftPaddle1"\n'),
        _result('as 1 "Gamepad:Button:LeftPaddle1"\n'),
        _result(
            'as 2 "Gamepad:Button:LeftPaddle1" '
            '"Gamepad:Button:RightPaddle1"\n'
        ),
    ])
    dbus = IpDbus(run=lambda _args: next(responses), event_cb=events.append)

    dbus.capabilities()
    dbus.capabilities()
    dbus.capabilities()

    reads = [
        event for event in events
        if event["operation"] == "read_capabilities"
    ]
    assert [event["capability_count"] for event in reads] == [1, 2]


def test_missing_composite_discovery_is_logarithmically_sampled():
    events = []
    dbus = IpDbus(
        run=lambda _args: _result(returncode=1),
        event_cb=events.append,
    )

    for _ in range(8):
        assert dbus.capabilities() == []

    failures = [
        event for event in events
        if event["operation"] == "discover_composite"
    ]
    assert [event["failure_count"] for event in failures] == [1, 2, 4, 8]


def test_selects_composite_by_exact_expected_name():
    calls = []

    def run(args):
        calls.append(args)
        if args[1] == "tree":
            return _result(
                "├─/org/shadowblip/InputPlumber/CompositeDevice0\n"
                "└─/org/shadowblip/InputPlumber/CompositeDevice1\n"
            )
        if args[-1] == "Name":
            path = args[3]
            return _result(
                's "ASUS ROG Ally"\n'
                if path.endswith("1")
                else 's "Bluetooth Controller"\n'
            )
        if args[-1] == "SourceDevicePaths":
            return _result('as 1 "/sys/devices/virtual/input/input0"\n')
        if args[-1] == "Capabilities":
            return _result('as 1 "Gamepad:Button:LeftPaddle1"\n')
        raise AssertionError(args)

    dbus = IpDbus(run=run, expected_names=("ASUS ROG Ally",))
    assert dbus.capabilities() == ["Gamepad:Button:LeftPaddle1"]
    assert dbus.diagnostics()["composite_name"] == "ASUS ROG Ally"


def test_refuses_ambiguous_composite_without_expected_name():
    dbus = IpDbus(
        run=lambda _args: _result(
            "├─/org/shadowblip/InputPlumber/CompositeDevice0\n"
            "└─/org/shadowblip/InputPlumber/CompositeDevice1\n"
        )
    )
    assert dbus.capabilities() == []
    assert dbus.diagnostics()["last_operation"]["reason"] == "composite_ambiguous"


def test_force_feedback_enabled_has_exact_readback():
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice0\n"),
        _result("b true\n"),
        _result(),
        _result("b false\n"),
    ])
    dbus = IpDbus(run=lambda _args: next(responses))
    assert dbus.force_feedback_enabled() is True
    assert dbus.set_force_feedback_enabled(False) is True


def test_force_feedback_test_calls_rumble_and_stop():
    calls = []

    def run(args):
        calls.append(args)
        if args[1] == "tree":
            return _result("└─/org/shadowblip/InputPlumber/CompositeDevice0\n")
        return _result()

    dbus = IpDbus(run=run)
    assert dbus.rumble(0.7) is True
    assert dbus.stop_rumble() is True
    assert any(args[-2:] == ["d", "0.7"] for args in calls)
    assert any("Stop" in args for args in calls)


def test_source_device_paths_returns_only_nonempty_paths():
    responses = iter([
        _result("└─/org/shadowblip/InputPlumber/CompositeDevice0\n"),
        _result('as 3 "/dev/input/event2" "" "/dev/hidraw1"\n'),
    ])
    dbus = IpDbus(run=lambda _args: next(responses))

    assert dbus.source_device_paths() == [
        "/dev/input/event2",
        "/dev/hidraw1",
    ]


def test_supported_target_ids_come_from_manager_property():
    calls = []

    def run(args):
        calls.append(args)
        return _result('as 4 "xb360" "xbox-elite" "keyboard" "mouse"\n')

    dbus = IpDbus(run=run)

    assert dbus.supported_target_device_ids() == [
        "xb360", "xbox-elite", "keyboard", "mouse",
    ]
    assert calls == [[
        "busctl", "get-property", "org.shadowblip.InputPlumber",
        "/org/shadowblip/InputPlumber/Manager",
        "org.shadowblip.InputManager", "SupportedTargetDeviceIds",
    ]]


def test_target_device_types_require_every_exact_target_property():
    def run(args):
        if args[1] == "tree":
            return _result(
                "└─/org/shadowblip/InputPlumber/CompositeDevice0\n"
            )
        if args[-1] == "TargetDevices":
            return _result(
                'as 3 "/org/shadowblip/InputPlumber/target/gamepad0" '
                '"/org/shadowblip/InputPlumber/target/keyboard0" ""\n'
            )
        if args[-1] == "DeviceType":
            return _result(
                's "xbox-elite"\n'
                if args[3].endswith("gamepad0")
                else 's "keyboard"\n'
            )
        raise AssertionError(args)

    dbus = IpDbus(run=run)

    assert dbus.target_device_types() == ["xbox-elite", "keyboard"]


def test_set_target_devices_calls_exact_composite_dbus_signature():
    calls = []

    def run(args):
        calls.append(args)
        if args[1] == "tree":
            return _result(
                "└─/org/shadowblip/InputPlumber/CompositeDevice3\n"
            )
        return _result()

    dbus = IpDbus(run=run)

    assert dbus.set_target_devices([
        "ds5-edge", "mouse", "keyboard", "touchpad",
    ]) is True
    assert calls[-1] == [
        "busctl", "call", "org.shadowblip.InputPlumber",
        "/org/shadowblip/InputPlumber/CompositeDevice3",
        "org.shadowblip.Input.CompositeDevice", "SetTargetDevices", "as",
        "4", "ds5-edge", "mouse", "keyboard", "touchpad",
    ]


def test_write_revalidates_cached_composite_identity():
    changed = False

    def run(args):
        nonlocal changed
        if args[1] == "tree":
            return _result(
                "└─/org/shadowblip/InputPlumber/CompositeDevice0\n"
            )
        if args[-1] == "Name":
            return _result(
                's "Bluetooth Controller"\n'
                if changed else 's "Lenovo Legion Go"\n'
            )
        if args[-1] == "SourceDevicePaths":
            return _result('as 1 "/dev/input/event2"\n')
        if args[-1] == "Capabilities":
            return _result('as 1 "Gamepad:Button:LeftPaddle1"\n')
        if "Rumble" in args:
            raise AssertionError("must not write to a changed composite")
        return _result()

    dbus = IpDbus(run=run, expected_names=("Lenovo Legion Go",))
    assert dbus.capabilities() == ["Gamepad:Button:LeftPaddle1"]
    changed = True

    assert dbus.rumble(1.0) is False
    assert dbus.diagnostics()["composite_path_available"] is False
