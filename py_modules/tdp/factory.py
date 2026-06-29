from tdp.backend import NullBackend, TDPBackend
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.ryzenadj import RyzenadjBackend
from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits


def _candidates(device, fallback, root, ryzenadj):
    key = device.key
    if key.startswith("steam_deck"):
        return [SteamDeckHwmonBackend(fallback, root=root), ryzenadj()]
    if key.startswith("rog_"):
        return [FirmwareAttrBackend("asus-armoury", fallback, root=root), ryzenadj()]
    if key.startswith("legion_"):
        return [FirmwareAttrBackend("lenovo-wmi-other", fallback, root=root,
                                    profile_name="lenovo-wmi-gamezone"), ryzenadj()]
    if key == "msi_claw_8_ai_plus":
        return [FirmwareAttrBackend("msi-wmi-platform", fallback, root=root)]
    # generic / other AMD
    return [ryzenadj()]


def select_backend(device, root="/", ryzenadj_resolve=None) -> TDPBackend:
    """Pick the first supported TDP strategy for the detected device; else NullBackend."""
    fallback = TdpLimits.from_profile(device)

    def ryzenadj():
        if ryzenadj_resolve is not None:
            return RyzenadjBackend(fallback, resolve=ryzenadj_resolve)
        return RyzenadjBackend(fallback)

    for backend in _candidates(device, fallback, root, ryzenadj):
        if backend.supported:
            return backend
    return NullBackend(f"no supported TDP interface for {device.key}")
