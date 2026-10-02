"""Manual TDP headroom past the manufacturer's safe range.

Matches what SimpleDeckyTDP lets a player request: up to 40 W on AMD handhelds and
120 W on Strix Halo, charger only. The firmware may still refuse or clamp it; presets
and Auto-TDP never enter this range.
"""

EXTRA_MAX_W = 40
STRIX_HALO_EXTRA_MAX_W = 120


def is_strix_halo(device) -> bool:
    return "Ryzen AI Max" in getattr(device, "chip", "")


def extra_tdp_max_ac(device) -> int | None:
    """Charger ceiling a manual request may reach, or None when the device has none."""
    if getattr(device, "vendor", None) != "amd":
        return None
    if getattr(device, "desktop_mode", False) or device.key.startswith("steam_"):
        return None
    ceiling = STRIX_HALO_EXTRA_MAX_W if is_strix_halo(device) else EXTRA_MAX_W
    return ceiling if ceiling > device.tdp_max_charger else None
