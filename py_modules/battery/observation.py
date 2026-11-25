_STATUSES = frozenset({"Charging", "Discharging", "Not charging", "Full", "Unknown"})


def _safe(reader):
    try:
        return reader()
    except Exception:  # noqa: BLE001
        return None


def _int_in(value, low, high):
    return value if type(value) is int and low <= value <= high else None


def observe_before_apply(backend, battery, read_on_ac) -> dict:
    """What the firmware left before Panel reasserts the threshold.

    Only reached on reassertions (start, resume, AC change, user change), so the
    reads cost no polling. Unreadable or out-of-range values stay None.
    """
    observed = _safe(lambda: battery.read())
    observed = observed if isinstance(observed, dict) else {}
    status = observed.get("status")
    ac = _safe(read_on_ac)
    return {
        "readback": _int_in(_safe(lambda: backend.get()), 0, 100),
        "battery_percent": _int_in(observed.get("percent"), 0, 100),
        "battery_status": status if status in _STATUSES else None,
        "energy_now_mwh": _int_in(observed.get("energy_now_mwh"), 0, 10_000_000),
        "energy_full_mwh": _int_in(observed.get("energy_full_mwh"), 1, 10_000_000),
        "ac_online": ac if type(ac) is bool else None,
    }


def worth_logging(before: dict, requested, adjustable: bool) -> bool:
    """Threshold lost, or battery above it off the charger, while Panel was not running.

    On/off backends (Lenovo) cap in firmware, so the stored percent means nothing there.
    """
    if not adjustable or type(requested) is not int:
        return False
    readback = before.get("readback")
    percent = before.get("battery_percent")
    return (readback is not None and readback != requested) or (
        percent is not None and percent > requested and before.get("ac_online") is not True
    )
