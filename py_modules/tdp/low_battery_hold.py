from dataclasses import dataclass


LOW_BATTERY_PERCENT = 20
PRIMARY_REASSERT_S = 15.0
LEGION_GO_S_REASSERT_S = 2.0

_REASSERT_BY_STRATEGY = {
    "primary": PRIMARY_REASSERT_S,
    "legion-go-s-83n6": LEGION_GO_S_REASSERT_S,
}


@dataclass(frozen=True)
class HoldDecision:
    available: bool
    enabled: bool
    active: bool
    strategy: str | None
    reassert_s: float | None
    reason: str
    battery_percent: int | None


def decide_hold(
    *,
    strategy,
    enabled,
    battery,
    on_ac,
    control_enabled,
    write_authorized,
    custom_mode,
    auto_tdp,
):
    available = strategy in _REASSERT_BY_STRATEGY
    percent = battery.get("percent") if isinstance(battery, dict) else None
    present = battery.get("present") is True if isinstance(battery, dict) else False
    status = str(battery.get("status") or "").strip().casefold() if present else ""
    try:
        percent = int(percent) if percent is not None else None
    except (TypeError, ValueError):
        percent = None

    reason = "active"
    if not available:
        reason = "unsupported"
    elif not enabled:
        reason = "disabled"
    elif on_ac:
        reason = "on_ac"
    elif not present:
        reason = "battery_absent"
    elif status in ("charging", "full"):
        reason = "battery_charging"
    elif percent is None:
        reason = "battery_unreadable"
    elif percent > LOW_BATTERY_PERCENT:
        reason = "battery_above_threshold"
    elif not control_enabled:
        reason = "control_disabled"
    elif not write_authorized:
        reason = "external_owner"
    elif not custom_mode:
        reason = "firmware_mode"
    elif auto_tdp:
        reason = "auto_tdp"

    active = reason == "active"
    return HoldDecision(
        available=available,
        enabled=bool(enabled) if available else False,
        active=active,
        strategy=strategy if available else None,
        reassert_s=_REASSERT_BY_STRATEGY[strategy] if active else None,
        reason=reason,
        battery_percent=percent,
    )
