_POWER_MODES = frozenset({"free", "silent", "balanced", "performance", "custom"})


def normalize_desktop_settings(settings: dict) -> bool:
    """Fail closed on malformed persisted desktop values before they reach hardware."""
    normalized = {
        "_desktop_defaults_migrated": (
            settings.get("_desktop_defaults_migrated") is True
        ),
        "desktop_mode_enabled": settings.get("desktop_mode_enabled") is True,
        "desktop_power_mode": (
            settings.get("desktop_power_mode")
            if settings.get("desktop_power_mode") in _POWER_MODES
            else "free"
        ),
        "desktop_cpu_w": _bounded_int(settings.get("desktop_cpu_w"), 23, 4, 30),
        "desktop_gpu_w": _bounded_int(settings.get("desktop_gpu_w"), 80, 1, 1000),
        "desktop_prev_tdp_control": (
            settings.get("desktop_prev_tdp_control")
            if isinstance(settings.get("desktop_prev_tdp_control"), bool)
            else None
        ),
        "fremont_fan_handoff_pending": (
            settings.get("fremont_fan_handoff_pending")
            if isinstance(settings.get("fremont_fan_handoff_pending"), bool)
            else True
        ),
    }
    changed = any(settings.get(key) != value for key, value in normalized.items())
    settings.update(normalized)
    return changed


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(minimum, min(maximum, value))


def effective_desktop_mode(device, manual_enabled: bool) -> bool:
    return bool(
        getattr(device, "desktop_mode", False)
        or (getattr(device, "is_generic", False) and manual_enabled is True)
    )


def recognised_desktop_migration_pending(settings: dict, device) -> bool:
    handoff = settings.get("desktop_power_handoff")
    return bool(
        getattr(device, "key", None) != "steam_machine"
        and not getattr(device, "is_generic", False)
        and settings.get("desktop_mode_enabled") is True
        and isinstance(handoff, dict)
        and handoff.get("device_key") == "generic"
    )


def migrate_desktop_defaults(settings: dict, device) -> bool:
    """Seed Fremont once into pass-through mode without changing any other host.

    Existing users keep every later choice because the marker is durable. Generic
    desktop opt-in also stays a pure UI/capability choice and never rewrites the
    handheld TDP master switch.
    """
    key = getattr(device, "key", None)
    if recognised_desktop_migration_pending(settings, device):
        return False
    if (
        key != "steam_machine"
        and not getattr(device, "is_generic", False)
        and settings.get("desktop_mode_enabled") is True
    ):
        previous = settings.get("desktop_prev_tdp_control")
        settings["desktop_mode_enabled"] = False
        settings["desktop_power_mode"] = "free"
        settings["desktop_prev_tdp_control"] = None
        if isinstance(previous, bool):
            settings["tdp_control_enabled"] = previous
        return True
    if key != "steam_machine":
        return False
    if settings.get("_desktop_defaults_migrated") is True:
        return False
    settings["desktop_power_mode"] = "free"
    settings["tdp_control_enabled"] = False
    settings["_desktop_defaults_migrated"] = True
    return True
