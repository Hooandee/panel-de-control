from controllers.capabilities import report, surface
from controllers.diagnostics import IntegratedDiagnostics


def _write_supply(root, name, **fields):
    path = root / "sys" / "class" / "power_supply" / name
    path.mkdir(parents=True)
    for field, value in fields.items():
        (path / field).write_text(str(value))


def test_system_battery_is_not_controller_battery(tmp_path):
    _write_supply(tmp_path, "BAT0", scope="System", capacity="80")

    state = IntegratedDiagnostics(root=str(tmp_path)).snapshot(
        "legion_go", {}
    )

    assert state["batteries"] == []


def test_detachable_battery_requires_exact_registry_match(tmp_path):
    _write_supply(
        tmp_path, "legion_go_left", scope="Device", capacity="73"
    )

    state = IntegratedDiagnostics(root=str(tmp_path)).snapshot(
        "legion_go", {}
    )

    assert state["batteries"] == []


def test_empty_snapshot_has_stable_shape():
    assert IntegratedDiagnostics.empty("generic") == {
        "device_key": "generic",
        "sources": [],
        "batteries": [],
        "inputs": {},
        "motion": None,
        "vibration": None,
        "last_operations": {},
    }


def test_snapshot_uses_only_redacted_manager_metadata_and_capabilities():
    vibration = surface(
        "native",
        "supported",
        fields={"mode": "dual", "left": 50, "right": 60},
        scope=("global", "game"),
        apply="hot",
        readback="exact",
        evidence="upstream",
    )
    buttons = surface(
        "inputplumber",
        "supported",
        fields={"buttons": [{"source": "LeftPaddle1", "label": "M2"}]},
        scope=("global", "game"),
        apply="hot",
        readback="exact",
        evidence="upstream",
    )
    manager_state = {
        "manager": "inputplumber",
        "manager_version": "0.78",
        "capabilities": report(
            "rog_ally", "inputplumber",
            {"buttons": buttons, "vibration": vibration},
        ),
        "dbus": {
            "composite_name": "ROG Ally",
            "source_device_count": 3,
            "raw_path": "/dev/input/event4",
            "last_operation": {
                "operation": "load_profile",
                "ok": True,
                "raw_path": "/dev/input/event4",
            },
        },
    }

    state = IntegratedDiagnostics().snapshot("rog_ally", manager_state)

    assert state["sources"] == [{
        "manager": "inputplumber",
        "version": "0.78",
        "name": "ROG Ally",
        "source_count": 3,
    }]
    assert state["inputs"] == {
        "buttons": [{"source": "LeftPaddle1", "label": "M2"}],
    }
    assert state["vibration"] == vibration
    assert state["last_operations"] == {
        "manager": {"operation": "load_profile", "ok": True},
    }
    assert "/dev/input" not in repr(state)
