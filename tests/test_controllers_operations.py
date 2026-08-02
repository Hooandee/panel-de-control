from controllers.operations import OperationResult, OperationState


def _result(component, status, generation, *, appid="42", **values):
    return OperationResult(
        component=component,
        status=status,
        reason=values.get("reason"),
        owner=values.get("owner", "native"),
        generation=generation,
        appid=appid,
        desired=values.get("desired", {}),
        actual=values.get("actual"),
    )


def test_old_generation_cannot_replace_new_confirmation():
    state = OperationState()
    old = state.start("10", {"vibration": {"value": 20}})
    new = state.start("20", {"vibration": {"value": 80}})

    assert state.publish(_result(
        "vibration", "applied", old, appid="10",
        desired={"value": 20}, actual={"value": 20},
    )) is False
    assert state.snapshot()["generation"] == new
    assert state.snapshot()["appid"] == "20"


def test_partial_results_remain_independent():
    state = OperationState()
    generation = state.start("42", {
        "buttons": {},
        "vibration": {"value": 40},
    })

    assert state.publish(_result(
        "buttons", "conflict", generation, reason="profile_conflict",
    )) is True
    assert state.publish(_result(
        "vibration", "applied", generation,
        desired={"value": 40}, actual={"value": 40},
    )) is True

    snapshot = state.snapshot()
    assert snapshot["components"]["buttons"]["status"] == "conflict"
    assert snapshot["components"]["vibration"]["status"] == "applied"


def test_snapshot_redacts_unknown_fields_and_reasons():
    state = OperationState()
    generation = state.start("42", {"vibration": {"value": 40}})

    assert state.publish(_result(
        "vibration", "failed", generation,
        reason="secret device output",
        desired={"value": 40, "path": "/dev/input/event9"},
    )) is False
    assert state.snapshot()["components"]["vibration"] == {
        "status": "pending",
        "desired": {"value": 40},
    }


def test_snapshot_is_detached_from_mutable_inputs_and_outputs():
    profile = {"vibration": {"value": 40}}
    state = OperationState()
    state.start("42", profile)
    profile["vibration"]["value"] = 100

    snapshot = state.snapshot()
    snapshot["components"]["vibration"]["desired"]["value"] = 0

    assert state.snapshot()["components"]["vibration"]["desired"] == {
        "value": 40,
    }


def test_unknown_component_or_status_is_never_published():
    state = OperationState()
    generation = state.start("42", {})

    assert state.publish(_result("lighting", "applied", generation)) is False
    assert state.publish(_result("buttons", "invented", generation)) is False
    assert state.snapshot()["components"] == {}


def test_lenovo_hd_vibration_fields_survive_operation_sanitizing():
    state = OperationState()
    desired = {
        "intensity": "high",
        "left_pattern": "fps",
        "right_pattern": "racing",
        "touchpad_enabled": False,
        "touchpad_intensity": "medium",
    }
    generation = state.start("42", {"vibration": desired})

    assert state.publish(_result(
        "vibration", "accepted_unverifiable", generation,
        desired=desired,
    )) is True
    assert state.snapshot()["components"]["vibration"]["desired"] == desired
