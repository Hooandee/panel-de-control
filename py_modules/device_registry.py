import dataclasses
import os

from cpu.info import read_cpu_model
from device_profiles import DEVICE_TABLE, GENERIC, DeviceProfile

def _read_product_name(root: str = "/") -> str:
    try:
        with open(os.path.join(root, "sys/class/dmi/id/product_name")) as handle:
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


def _generic_for(root: str) -> DeviceProfile:
    """GENERIC with the real silicon vendor + chip name read from the host, so an
    unrecognised handheld still picks the right per-vendor backend chain and shows
    its actual chip instead of "Desconocido". Vendor defaults to amd (the common
    case) when cpuinfo is unreadable."""
    vendor = _read_vendor(root) or GENERIC.vendor
    chip = read_cpu_model(root) or GENERIC.chip
    return dataclasses.replace(GENERIC, vendor=vendor, chip=chip)


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
    if "z2 a" in c:
        return "rdna2"  # lower-tier Z2
    # Strix Point / Strix Halo (Ryzen AI ...): RDNA 3.5
    if "ryzen ai" in c or "ai max" in c or "hx 370" in c or "hx 365" in c:
        return "rdna35"
    # Z1 Extreme / Z2 Go / Phoenix-Hawk (78x0/88x0): RDNA 3
    if "z1 extreme" in c or "z2 go" in c or "8840" in c or "7840" in c or "8640" in c:
        return "rdna3"
    return "unknown"


def detect(product_name: str | None = None, root: str = "/") -> DeviceProfile:
    """Return the DeviceProfile for this machine. Never raises. Falls back to a
    GENERIC profile carrying the host's real vendor/chip.
    `product_name`/`root` are injectable for tests; in production they read DMI."""
    name = product_name if product_name is not None else _read_product_name(root)
    lname = name.lower()
    for profile in DEVICE_TABLE:
        for needle in profile.match_names:
            if needle.lower() in lname:
                return profile
    return _generic_for(root)
