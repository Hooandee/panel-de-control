import math

from controllers.capabilities import clean_report, report, surface


def test_surface_preserves_explicit_semantics():
    assert surface(
        "native",
        "supported",
        fields={"left": {"min": 0, "max": 64, "step": 1}},
        scope=("global", "game"),
        apply="hot",
        readback="exact",
        evidence="upstream_and_physical",
    ) == {
        "owner": "native",
        "availability": "supported",
        "fields": {"left": {"min": 0, "max": 64, "step": 1}},
        "scope": ["global", "game"],
        "apply": "hot",
        "readback": "exact",
        "evidence": "upstream_and_physical",
    }


def test_surface_includes_an_explicit_reason_only_when_present():
    unavailable = surface(
        "none",
        "unavailable",
        fields={},
        scope=(),
        apply="read_only",
        readback="none",
        evidence="unknown",
        reason="No proven control route",
    )
    supported = surface(
        "inputplumber",
        "supported",
        fields={},
        scope=("global",),
        apply="hot",
        readback="accepted",
        evidence="upstream",
    )

    assert unavailable["reason"] == "No proven control route"
    assert "reason" not in supported


def test_report_preserves_device_manager_and_named_surfaces():
    vibration = surface(
        "native",
        "supported",
        fields={"enabled": True},
        scope=("global",),
        apply="hot",
        readback="exact",
        evidence="physical",
    )

    assert report("rog_ally", "inputplumber", {"vibration": vibration}) == {
        "device_key": "rog_ally",
        "manager": "inputplumber",
        "surfaces": {"vibration": vibration},
    }


def test_clean_report_rejects_unknown_semantics():
    dirty = report(
        "rog_ally",
        "inputplumber",
        {
            "vibration": {
                "owner": "native",
                "availability": "yes",
                "fields": {},
            }
        },
    )

    assert clean_report(dirty)["surfaces"] == {}


def test_clean_report_rejects_a_surface_missing_required_semantics():
    dirty = {
        "device_key": "legion_go",
        "manager": "inputplumber",
        "surfaces": {
            "vibration": {
                "owner": "inputplumber",
                "availability": "supported",
                "fields": {},
                "scope": ["global", "game"],
                "apply": "hot",
                "readback": "observed",
            }
        },
    }

    assert clean_report(dirty)["surfaces"] == {}


def test_clean_report_rejects_non_allowlisted_semantics():
    base = surface(
        "inputplumber",
        "supported",
        fields={},
        scope=("global", "game"),
        apply="hot",
        readback="observed",
        evidence="upstream",
    )

    for field, invalid in (
        ("availability", "yes"),
        ("apply", "restart"),
        ("readback", "true"),
        ("evidence", "assumed"),
        ("scope", ["session"]),
    ):
        candidate = {**base, field: invalid}
        dirty = report("legion_go", "inputplumber", {"vibration": candidate})
        assert clean_report(dirty)["surfaces"] == {}, field


def test_clean_report_rejects_unhashable_semantics_without_raising():
    dirty = report(
        "legion_go",
        "inputplumber",
        {
            "vibration": {
                "owner": "inputplumber",
                "availability": [],
                "fields": {},
                "scope": [{}],
                "apply": {},
                "readback": [],
                "evidence": {},
            }
        },
    )

    assert clean_report(dirty)["surfaces"] == {}


def test_clean_report_keeps_json_safe_fields_up_to_two_nested_levels():
    valid = surface(
        "inputplumber",
        "experimental",
        fields={
            "enabled": True,
            "gain": 0.5,
            "label": "Vibration",
            "unset": None,
            "motor": {"min": 0, "max": 100, "steps": [0, 20, 40]},
            "modes": [{"id": "xbox", "recreate": True}],
        },
        scope=("game",),
        apply="recreate",
        readback="accepted",
        evidence="upstream",
    )

    assert clean_report(report(None, "inputplumber", {"vibration": valid})) == {
        "device_key": None,
        "manager": "inputplumber",
        "surfaces": {"vibration": valid},
    }


def test_clean_report_rejects_non_json_and_over_nested_fields():
    for fields in (
        {"gain": math.nan},
        {"value": object()},
        {"too_deep": {"level_two": {"level_three": {"value": 1}}}},
        {1: "non-string key"},
    ):
        dirty = report(
            "rog_ally",
            "inputplumber",
            {
                "vibration": surface(
                    "native",
                    "supported",
                    fields=fields,
                    scope=("global",),
                    apply="hot",
                    readback="exact",
                    evidence="physical",
                )
            },
        )
        assert clean_report(dirty)["surfaces"] == {}


def test_clean_report_rejects_malformed_report_shell_and_surface_names():
    assert clean_report(None) == {
        "device_key": None,
        "manager": "unknown",
        "surfaces": {},
    }
    assert clean_report(
        {"device_key": 42, "manager": [], "surfaces": {1: {}}}
    ) == {
        "device_key": None,
        "manager": "unknown",
        "surfaces": {},
    }
