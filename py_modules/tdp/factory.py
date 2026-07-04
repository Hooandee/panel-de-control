from tdp.backend import NullBackend, TDPBackend
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.intel_rapl import IntelRaplBackend
from tdp.ryzenadj import RyzenadjBackend
from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits


def _candidates(device, fallback, root, ryzenadj):
    """Ordered probe chain of backend factories (constructed lazily by the caller,
    so an early match costs no extra sysfs work). The detected family puts its
    known-good backend first, then falls through to every other known path by
    capability — so a known device stays robust if a kernel update moves its
    interface, and an unrecognised handheld still lands on whatever it actually
    exposes. ryzenadj (AMD-only) is excluded on Intel hosts so its mere presence
    can't capture the selection."""
    def asus():
        return FirmwareAttrBackend("asus-armoury", fallback, root=root)

    def lenovo():
        return FirmwareAttrBackend("lenovo-wmi-other", fallback, root=root,
                                   profile_name="lenovo-wmi-gamezone")

    def msi():
        return FirmwareAttrBackend("msi-wmi-platform", fallback, root=root)

    def intel():
        return IntelRaplBackend(fallback, root=root)

    def deck():
        return SteamDeckHwmonBackend(fallback, root=root)

    key = device.key
    if device.vendor == "intel":
        return [msi, intel]
    if key.startswith("steam_deck"):
        return [deck, asus, lenovo, msi, ryzenadj]
    if key.startswith("rog_"):
        return [asus, lenovo, msi, ryzenadj]
    if key.startswith("legion_"):
        return [lenovo, asus, msi, ryzenadj]
    # generic / other AMD. intel-rapl excluded (AMD RAPL can confirm a write without
    # changing real TDP); deck excluded (steamdeck-hwmon matches any power*_cap chip,
    # incl. amdgpu's GPU cap — wrong rail). ryzenadj is the AMD fallback.
    return [asus, lenovo, msi, ryzenadj]


def select_backend(device, root="/", ryzenadj_resolve=None) -> TDPBackend:
    """Pick the first supported TDP strategy for the detected device; else NullBackend."""
    fallback = TdpLimits.from_profile(device)

    def ryzenadj():
        if ryzenadj_resolve is not None:
            return RyzenadjBackend(fallback, resolve=ryzenadj_resolve)
        return RyzenadjBackend(fallback)

    for make in _candidates(device, fallback, root, ryzenadj):
        backend = make()
        if backend.supported:
            return backend
    return NullBackend(f"no supported TDP interface for {device.key}")
