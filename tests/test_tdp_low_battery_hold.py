from tdp.low_battery_hold import decide_hold


def _battery(percent):
    return {
        "present": True,
        "percent": percent,
        "status": "Discharging",
    }


def test_hold_activates_at_the_twenty_percent_boundary():
    decision = decide_hold(
        strategy="primary",
        enabled=True,
        battery=_battery(20),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )

    assert decision.available is True
    assert decision.active is True
    assert decision.reassert_s == 15.0
    assert decision.reason == "active"


def test_hold_leaves_the_tdp_path_untouched_when_disabled():
    decision = decide_hold(
        strategy="primary",
        enabled=False,
        battery=_battery(10),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )

    assert decision.available is True
    assert decision.active is False
    assert decision.reassert_s is None
    assert decision.reason == "disabled"


def test_hold_requires_a_readable_battery_below_the_threshold():
    unreadable = decide_hold(
        strategy="primary",
        enabled=True,
        battery=_battery(None),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )
    above_threshold = decide_hold(
        strategy="primary",
        enabled=True,
        battery=_battery(21),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )

    assert unreadable.active is False
    assert unreadable.reason == "battery_unreadable"
    assert above_threshold.active is False
    assert above_threshold.reason == "battery_above_threshold"


def test_hold_requires_a_present_battery_that_is_not_charging():
    common = {
        "strategy": "primary",
        "enabled": True,
        "on_ac": False,
        "control_enabled": True,
        "write_authorized": True,
        "custom_mode": True,
        "auto_tdp": False,
    }

    absent = decide_hold(
        **common,
        battery={"present": False, "percent": 10, "status": "Discharging"},
    )
    charging = decide_hold(
        **common,
        battery={"present": True, "percent": 10, "status": "Charging"},
    )

    assert absent.active is False
    assert absent.reason == "battery_absent"
    assert charging.active is False
    assert charging.reason == "battery_charging"


def test_hold_does_not_compete_with_charger_auto_tdp_or_an_external_owner():
    common = {
        "strategy": "primary",
        "enabled": True,
        "battery": _battery(10),
        "control_enabled": True,
        "write_authorized": True,
        "custom_mode": True,
        "auto_tdp": False,
    }

    assert decide_hold(**common, on_ac=True).reason == "on_ac"
    assert decide_hold(**{**common, "on_ac": False, "auto_tdp": True}).reason == "auto_tdp"
    assert decide_hold(
        **{**common, "on_ac": False, "write_authorized": False}
    ).reason == "external_owner"


def test_unverified_backends_do_not_offer_the_hold():
    decision = decide_hold(
        strategy=None,
        enabled=True,
        battery=_battery(10),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )

    assert decision.available is False
    assert decision.active is False
    assert decision.reason == "unsupported"


def test_legion_go_s_uses_the_faster_exact_route():
    decision = decide_hold(
        strategy="legion-go-s-83n6",
        enabled=True,
        battery=_battery(10),
        on_ac=False,
        control_enabled=True,
        write_authorized=True,
        custom_mode=True,
        auto_tdp=False,
    )

    assert decision.active is True
    assert decision.reassert_s == 2.0
