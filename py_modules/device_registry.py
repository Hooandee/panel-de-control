import dataclasses
import os

from cpu.info import read_cpu_model
import device_tree
from device_profiles import (
    ARM_DEVICE_TABLE,
    DESKTOP_PC,
    DEVICE_TABLE,
    GENERIC,
    GENERIC_ARM,
    DeviceProfile,
)

# SMBIOS chassis types that can carry a battery or be held (portable, laptop,
# notebook, hand held, docking station, sub notebook, tablet, convertible,
# detachable). Many handheld BIOSes report "Desktop", so chassis alone never
# proves a desktop: the host must also lack a system battery.
_PORTABLE_CHASSIS = frozenset({"8", "9", "10", "11", "12", "14", "30", "31", "32"})

def _read_dmi(root: str, field: str) -> str:
    try:
        with open(os.path.join(root, "sys/class/dmi/id", field)) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _read_vendor(root: str = "/") -> str | None:
    try:
        with open(os.path.join(root, "proc", "cpuinfo")) as handle:
            for line in handle:
                if line.startswith("vendor_id"):
                    value = line.split(":", 1)[1]
                    if "Intel" in value:
                        return "intel"
                    if "AMD" in value:
                        return "amd"
                    return None
    except OSError:
        return None
    return None


def _has_system_battery(root: str) -> bool | None:
    supplies = os.path.join(root, "sys/class/power_supply")
    try:
        names = os.listdir(supplies)
    except OSError:
        return None
    for name in names:
        base = os.path.join(supplies, name)
        if _read_file(os.path.join(base, "type")) != "Battery":
            continue
        if _read_file(os.path.join(base, "scope")) != "Device":
            return True
    return False


def _read_file(path: str) -> str:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _is_desktop_host(root: str) -> bool:
    chassis = _read_dmi(root, "chassis_type")
    if not chassis or chassis in _PORTABLE_CHASSIS:
        return False
    return _has_system_battery(root) is False


def _generic_for(root: str) -> DeviceProfile:
    """GENERIC with the real silicon vendor + chip name read from the host, so an
    unrecognised handheld still picks the right per-vendor backend chain and shows
    its actual chip instead of "Desconocido". Vendor defaults to amd (the common
    case) when cpuinfo is unreadable."""
    vendor = _read_vendor(root) or GENERIC.vendor
    chip = read_cpu_model(root) or GENERIC.chip
    base = DESKTOP_PC if _is_desktop_host(root) else GENERIC
    return dataclasses.replace(base, vendor=vendor, chip=chip)


def _detect_arm(root: str) -> DeviceProfile:
    tree = device_tree.read_device_tree(root)
    compatible = set(tree.compatible)
    chip = device_tree.soc_name(tree, root)
    for profile in ARM_DEVICE_TABLE:
        if compatible.intersection(profile.dt_compatible):
            return dataclasses.replace(profile, chip=chip or profile.chip)
    return dataclasses.replace(
        GENERIC_ARM,
        display_name=tree.model or GENERIC_ARM.display_name,
        chip=chip or GENERIC_ARM.chip,
        vendor=device_tree.soc_vendor(tree) or GENERIC_ARM.vendor,
    )


def gpu_generation(vendor: str, chip: str) -> str:
    """AMD RDNA generation (or "intel"/"unknown") derived from the real chip name,
    used to gate FSR/XeSS upgrade launch options. Best-effort by silicon family;
    a wrong guess only shows/hides an upscaler pill. FSR4 = rdna3/rdna4 only.
    """
    if (vendor or "").lower() == "intel":
        return "intel"
    c = (chip or "").lower()
    if "van gogh" in c or "sephiroth" in c:
        return "rdna2"  # Steam Deck
    # Z2 A and Z2 Go are RDNA 2 class (no FSR4); keep them off the FSR4 path.
    if "z2 a" in c or "z2 go" in c:
        return "rdna2"
    # Strix Point / Strix Halo (Ryzen AI ...): RDNA 3.5
    if "ryzen ai" in c or "ai max" in c or "hx 370" in c or "hx 365" in c:
        return "rdna35"
    # Z1 Extreme / Phoenix-Hawk (78x0/88x0): RDNA 3
    if "z1 extreme" in c or "8840" in c or "7840" in c or "8640" in c:
        return "rdna3"
    return "unknown"


def detect(product_name: str | None = None, root: str = "/") -> DeviceProfile:
    """Return the DeviceProfile for this machine. Never raises. Falls back to a
    GENERIC profile carrying the host's real vendor/chip.
    `product_name`/`root` are injectable for tests; in production they read DMI."""
    name = product_name if product_name is not None else _read_dmi(root, "product_name")
    sys_vendor = _read_dmi(root, "sys_vendor")
    board_name = _read_dmi(root, "board_name")
    lname = name.lower()
    for profile in DEVICE_TABLE:
        if profile.dmi_matches:
            if any(match.matches(name, sys_vendor, board_name) for match in profile.dmi_matches):
                return profile
            continue
        for needle in profile.match_names:
            if needle.lower() in lname:
                return profile
    if device_tree.is_arm(root):
        return _detect_arm(root)
    return _generic_for(root)
