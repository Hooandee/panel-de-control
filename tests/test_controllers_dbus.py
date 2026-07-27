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
