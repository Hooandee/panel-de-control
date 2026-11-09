import dataclasses
import os
import re

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


def gpu_generation(vendor: str, chip: str, root: str = "") -> str:
    """AMD RDNA generation (or "intel"/"unknown") from the chip name, else from the GPU's PCI id when `root` is
    given. It only shapes suggestions: Panel never refuses an upscaler over it."""
    if (vendor or "").lower() == "intel":
        return "intel"
    c = (chip or "").lower()
    if "van gogh" in c or "sephiroth" in c or "custom apu 0405" in c or "custom apu 0932" in c:
        return "rdna2"  # Steam Deck: family names, or Valve's APU codes as /proc/cpuinfo reports them
    # Strix Point / Strix Halo, including the Z2 Extreme with or without "AI" in its name: RDNA 3.5
    if "ryzen ai" in c or "ai max" in c or "hx 370" in c or "hx 365" in c or "z2 extreme" in c:
        return "rdna35"
    # Z2 A and Z2 Go are RDNA 2 class (no FSR4 Full).
    if "z2 a" in c or "z2 go" in c:
        return "rdna2"
    # Rembrandt laptops and handhelds (6800U, 6600U, 7735U...): RDNA 2
    if re.search(r"\b6[89]00(?:u|hs|hx|h)\b|\b6600u\b|\b7[3-7]35(?:u|hs|h)\b", c):
        return "rdna2"
    # Z1, Z1 Extreme and Z2 (Phoenix / Hawk Point) and their laptop siblings: RDNA 3
    if re.search(r"\bz1\b|\bz2\b|7840|8840|8640|7640|8540|7540", c):
        return "rdna3"
    return pci_gpu_generation(root) if root else "unknown"


# AMD integrated GPUs by PCI device id, for chips whose name says nothing (a custom APU, a new model).
_AMD_PCI = {
    "0x163f": "rdna2", "0x1435": "rdna2", "0x1681": "rdna2",            # Van Gogh, Sephiroth, Rembrandt (Z2 Go)
    "0x15bf": "rdna3", "0x15c8": "rdna3", "0x1900": "rdna3", "0x1901": "rdna3",  # Phoenix, Phoenix 2, Hawk Point
    "0x150e": "rdna35", "0x1586": "rdna35", "0x1114": "rdna35",          # Strix Point, Strix Halo, Krackan
    # Discrete Radeon: RX 6000, RX 7000, RX 9000
    "0x73bf": "rdna2", "0x73df": "rdna2", "0x73ef": "rdna2", "0x73ff": "rdna2", "0x743f": "rdna2",
    "0x744c": "rdna3", "0x747e": "rdna3", "0x7480": "rdna3", "0x7483": "rdna3",
    "0x7550": "rdna4", "0x7590": "rdna4",
}


def pci_gpu_generation(root: str = "/") -> str:
    base = os.path.join(root, "sys/class/drm")
    try:
        cards = sorted(name for name in os.listdir(base) if re.fullmatch(r"card\d+", name))
    except OSError:
        return "unknown"
    amd = False
    for card in cards:
        device = os.path.join(base, card, "device")
        try:
            with open(os.path.join(device, "vendor")) as f:
                vendor = f.read().strip().lower()
            with open(os.path.join(device, "device")) as f:
                identifier = f.read().strip().lower()
        except OSError:
            continue
        if vendor == "0x8086":
            return "intel"
        if vendor == "0x1002":
            amd = True
            if identifier in _AMD_PCI:
                return _AMD_PCI[identifier]
    # An AMD GPU this table doesn't know yet: newer than the table, so RDNA 3 class at least.
    return "rdna3" if amd else "unknown"


def gpu_pci(root: str = "/") -> list[dict]:
    """Each display GPU's PCI vendor and device id, for reports: enough to tell the real chip when its name doesn't."""
    base = os.path.join(root, "sys/class/drm")
    try:
        cards = sorted(name for name in os.listdir(base) if re.fullmatch(r"card\d+", name))
    except OSError:
        return []
    found = []
    for card in cards[:4]:
        values = {}
        for field in ("vendor", "device"):
            try:
                with open(os.path.join(base, card, "device", field)) as f:
                    value = f.read().strip().lower()
            except OSError:
                break
            if not re.fullmatch(r"0x[0-9a-f]{4}", value):
                break
            values[field] = value
        else:
            found.append({"card": card, **values})
    return found


def gpu_facts(vendor: str, chip: str, root: str = "/") -> dict:
    """The generation Panel uses and where it came from: the chip's name, its PCI id, or neither."""
    by_name = gpu_generation(vendor, chip)
    generation = by_name if by_name != "unknown" else gpu_generation(vendor, chip, root)
    source = "name" if by_name != "unknown" else "pci" if generation != "unknown" else "unknown"
    return {"generation": generation, "source": source, "pci": gpu_pci(root)}


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
