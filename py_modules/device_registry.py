import dataclasses
import json
import logging
import os
import re
from pathlib import Path

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


_GPU_RULES_PATH = Path(__file__).resolve().parents[1] / "shared" / "upscalers" / "gpus.json"
_NO_GPU_RULES = {"vendors": {}, "name_rules": [], "pci_vendors": {}, "amd_pci": {}, "unknown_amd": "unknown"}


def _load_gpu_rules(path: Path = _GPU_RULES_PATH) -> dict:
    """The GPU family rules Windows reads too. Without them every family is "unknown": upscaler suggestions get
    vaguer, but device detection and everything else keep working."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rules = {
            "vendors": {str(key).lower(): str(value) for key, value in raw["vendors"].items()},
            "name_rules": [(str(rule["generation"]), tuple(str(text) for text in rule.get("contains", ())),
                            re.compile(rule["pattern"]) if rule.get("pattern") else None) for rule in raw["name_rules"]],
            "pci_vendors": {str(key).lower(): str(value) for key, value in raw["pci_vendors"].items()},
            "amd_pci": {str(key).lower(): str(value) for key, value in raw["amd_pci"].items()},
            "unknown_amd": str(raw["unknown_amd"]),
        }
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported_schema")
        return rules
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as error:
        logging.getLogger(__name__).warning("GPU family rules unavailable (%s): every GPU reads as unknown", error)
        return dict(_NO_GPU_RULES)


_GPU_RULES = _load_gpu_rules()


def gpu_generation(vendor: str, chip: str, root: str = "") -> str:
    """AMD RDNA generation (or "intel"/"unknown") from the chip name, else from the GPU's PCI id when `root` is
    given. It only shapes suggestions: Panel never refuses an upscaler over it."""
    by_vendor = _GPU_RULES["vendors"].get((vendor or "").lower())
    if by_vendor:
        return by_vendor
    c = (chip or "").lower()
    for generation, contains, pattern in _GPU_RULES["name_rules"]:
        if any(text in c for text in contains) or (pattern is not None and pattern.search(c)):
            return generation
    return pci_gpu_generation(root) if root else "unknown"


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
        kind = _GPU_RULES["pci_vendors"].get(vendor)
        if kind == "intel":
            return "intel"
        if kind == "amd":
            amd = True
            if identifier in _GPU_RULES["amd_pci"]:
                return _GPU_RULES["amd_pci"][identifier]
    # An AMD GPU the table doesn't know yet: newer than the table, so RDNA 3 class at least.
    return _GPU_RULES["unknown_amd"] if amd else "unknown"


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
