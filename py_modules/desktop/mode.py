def effective_desktop_mode(device, manual_enabled: bool) -> bool:
    return bool(getattr(device, "desktop_mode", False) or manual_enabled)


def migrate_desktop_defaults(settings: dict, device) -> bool:
    """Seed Fremont once into pass-through mode without changing any other host.

    Existing users keep every later choice because the marker is durable. Generic
    desktop opt-in also stays a pure UI/capability choice and never rewrites the
    handheld TDP master switch.
    """
    if getattr(device, "key", None) != "steam_machine":
        return False
    if settings.get("_desktop_defaults_migrated"):
        return False
    settings["desktop_power_mode"] = "free"
    settings["tdp_control_enabled"] = False
    settings["_desktop_defaults_migrated"] = True
    return True
