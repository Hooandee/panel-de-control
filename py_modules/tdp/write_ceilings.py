"""Write ceilings a device's opt-ins and manual extra range allow beyond its profile limits.

Backends clamp writes with these; the reported range only grows through main's limits,
so a backend accepting the ceiling never widens the UI on its own.
"""

from tdp.extra_range import extra_tdp_max_ac


def cooler_write_max(device) -> int | None:
    """Ceiling for both battery and charger when the external cooler is attached."""
    if getattr(device, "cooler_charger_only", False):
        return None
    return device.cooler_max


def charger_write_max(device) -> int | None:
    """Ceiling that only applies on the charger (charger-only cooler, warned unlock,
    manual extra range)."""
    ceilings = [getattr(device, "experimental_tdp_max_ac", None), extra_tdp_max_ac(device)]
    if getattr(device, "cooler_charger_only", False):
        ceilings.append(device.cooler_max)
    ceilings = [value for value in ceilings if value]
    return max(ceilings) if ceilings else None


def charger_cooler_max(device) -> int | None:
    """Charger-only cooler ceiling: safe once the player confirms the cooler is attached."""
    return device.cooler_max if getattr(device, "cooler_charger_only", False) else None
