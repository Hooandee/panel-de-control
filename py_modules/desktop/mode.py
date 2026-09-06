def effective_desktop_mode(device, manual_enabled: bool) -> bool:
    return bool(
        getattr(device, "desktop_mode", False)
        or (getattr(device, "is_generic", False) and manual_enabled)
    )


def recognised_desktop_migration_pending(settings: dict, device) -> bool:
    handoff = settings.get("desktop_power_handoff")
    return bool(
        getattr(device, "key", None) != "steam_machine"
        and not getattr(device, "is_generic", False)
        and settings.get("desktop_mode_enabled")
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
        and settings.get("desktop_mode_enabled")
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
    if settings.get("_desktop_defaults_migrated"):
        return False
    settings["desktop_power_mode"] = "free"
    settings["tdp_control_enabled"] = False
    settings["_desktop_defaults_migrated"] = True
    return True
