from device_quirks import (
    is_gpd_win_mini_2025,
    legion_go_s_83n6_rail_floors,
)
from tdp.alib import AlibBackend
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
    exposes. The generic AMD write paths (ryzenadj, then ALIB via acpi_call) sit
    strictly last, after every device-specific interface, so a recognised device
    never changes selection. Both are AMD-only and excluded on Intel."""
    generic = device.is_generic

    def asus():
        return FirmwareAttrBackend("asus-armoury", fallback, root=root, is_generic=generic)

    def lenovo():
        return FirmwareAttrBackend(
            "lenovo-wmi-other",
            fallback,
            root=root,
            profile_name="lenovo-wmi-gamezone",
            is_generic=generic,
            rail_floors=legion_go_s_83n6_rail_floors(device, root),
        )

    def msi():
        return FirmwareAttrBackend("msi-wmi-platform", fallback, root=root, is_generic=generic)

    def intel():
        return IntelRaplBackend(fallback, root=root)

    def deck():
        return SteamDeckHwmonBackend(fallback, device.key, root=root)

    def alib():
        return AlibBackend(fallback, root=root, write_max=device.cooler_max)

    # Generic-AMD fallbacks, appended after every device-specific path: ryzenadj
    # first, then the acpi_call ALIB path when ryzenadj is absent.
    amd_tail = [ryzenadj, alib]

    key = device.key
    if device.vendor == "intel":
        return [msi, intel]
    if key == "steam_machine":
        # Fremont's AMD Custom CPU 1772 is not a Ryzen Mobile model: physical
        # validation returns "unsupported model 124" from ryzenadj. A bundled
        # binary is therefore not a capability. Keep future firmware-attribute
        # paths discoverable, but never fall into write-only generic AMD methods.
        return [asus, lenovo, msi]
    if key.startswith("steam_deck"):
        return [deck]
    if key == "msi_claw_a8":
        return [ryzenadj]
    if key == "onexplayer_apex":
        return [alib, ryzenadj]
    if key.startswith("rog_"):
        return [asus, lenovo, msi, *amd_tail]
    if key.startswith("legion_"):
        return [lenovo, asus, msi, *amd_tail]
    # generic / other AMD. intel-rapl excluded (AMD RAPL can confirm a write without
    # changing real TDP); deck excluded (steamdeck-hwmon matches any power*_cap chip,
    # incl. amdgpu's GPU cap — wrong rail).
    return [asus, lenovo, msi, *amd_tail]


def select_backend(device, root="/", ryzenadj_resolve=None) -> TDPBackend:
    """Pick the first supported TDP strategy for the detected device; else NullBackend."""
    fallback = TdpLimits.from_profile(device)

    def ryzenadj():
        kwargs = {"resolve": ryzenadj_resolve} if ryzenadj_resolve is not None else {}
        return RyzenadjBackend(
            fallback,
            write_max=device.cooler_max,
            power_only_retry=is_gpd_win_mini_2025(device, root),
            **kwargs,
        )

    trace = []
    for make in _candidates(device, fallback, root, ryzenadj):
        candidate = make.__name__
        try:
            backend = make()
        except Exception as exc:  # noqa: BLE001
            trace.append({
                "candidate": candidate,
                "backend": None,
                "supported": False,
                "error": type(exc).__name__,
            })
            continue
        trace.append({
            "candidate": candidate,
            "backend": backend.name,
            "supported": bool(backend.supported),
        })
        if backend.supported:
            backend.probe_trace = tuple(trace)
            return backend
    backend = NullBackend(f"no supported TDP interface for {device.key}")
    backend.probe_trace = tuple(trace)
    return backend
