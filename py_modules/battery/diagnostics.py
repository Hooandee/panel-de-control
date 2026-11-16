_BATTERY_STATUSES = {"Charging", "Discharging", "Not charging", "Full", "Unknown"}


def _read(reader):
    try:
        return reader()
    except Exception:  # noqa: BLE001
        return None


def _percent(value):
    return value if type(value) is int and 0 <= value <= 100 else None


def capture_charge_limit_before(backend, battery, read_on_ac):
    """Observe before reapplying the threshold, without inferring charge behavior."""
    readback = _read(backend.get)
    observed = _read(battery.read)
    observed = observed if isinstance(observed, dict) else {}
    status = observed.get("status")
    ac = _read(read_on_ac)
    return {
        "readback": _percent(readback),
        "battery_percent": _percent(observed.get("percent")),
        "battery_status": status if isinstance(status, str) and status in _BATTERY_STATUSES else None,
        "ac_online": ac if type(ac) is bool else None,
    }
