import os

from device_quirks import (
    asus_tdp_authoritative_reassert_s,
    is_gpd_win_mini_2025_tdp_recovery,
    is_legion_go_s_83n6,
    legion_go_2_83n0_firmware_attr_quirks,
    legion_go_s_83l3_firmware_attr_quirks,
    legion_go_s_83n6_firmware_attr_quirks,
    legion_go_s_83n6_rail_floors,
)
from tdp.alib import AlibBackend
from tdp.amd_dptc import AmdDptcBackend
from tdp.asus_nb_wmi import AsusNbWmiBackend
from tdp.backend import NullBackend, TDPBackend
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.intel_rapl import IntelRaplBackend
from tdp.msi_claw_a8 import MsiClawA8FirmwareBackend
from tdp.ryzenadj import RyzenadjBackend
from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits


_RYZENADJ_ONLY_KEYS = frozenset({
    "onexplayer_superx",
    "zotac_gaming_zone",
    "rog_flow_z13",
    "onexplayer_f1",
    "gpd_win_mini_2025",
    "ayaneo_3",
})

_STRICT_RYZENADJ_KEYS = _RYZENADJ_ONLY_KEYS - {"gpd_win_mini_2025"}


def _runtime_lock_path(root, name):
    return os.path.join(root, "run/panel-de-control", name)


def _candidates(device, fallback, root, ryzenadj, os_id=None):
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
        return FirmwareAttrBackend(
            "asus-armoury",
            fallback,
            root=root,
            is_generic=generic,
            authoritative_reassert_s=asus_tdp_authoritative_reassert_s(
                device,
                root,
            ),
            trust_live_bounds=device.key == "rog_flow_z13",
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-asus-armoury.lock",
            ),
            restore_on_release=os_id == "anatase",
            ownership_lock_path=_runtime_lock_path(
                root,
                "ownership-asus-armoury.lock",
            ),
        )

    def lenovo():
        go_s_83l3 = legion_go_s_83l3_firmware_attr_quirks(device, root)
        backend = FirmwareAttrBackend(
            "lenovo-wmi-other",
            fallback,
            root=root,
            profile_name="lenovo-wmi-gamezone",
            is_generic=generic,
            rail_floors=legion_go_s_83n6_rail_floors(device, root),
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-lenovo-wmi-other.lock",
            ),
            **legion_go_2_83n0_firmware_attr_quirks(device, root),
            **go_s_83l3,
            **legion_go_s_83n6_firmware_attr_quirks(device, root),
        )
        if go_s_83l3:
            backend.low_battery_hold_strategy = None
        return backend

    def msi():
        return FirmwareAttrBackend(
            "msi-wmi-platform",
            fallback,
            root=root,
            is_generic=generic,
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-msi-wmi-platform.lock",
            ),
        )

    def intel():
        return IntelRaplBackend(fallback, root=root)

    def deck():
        return SteamDeckHwmonBackend(fallback, device.key, root=root)

    def asus_nb_wmi():
        return AsusNbWmiBackend(
            fallback,
            root=root,
            ownership_lock_path=_runtime_lock_path(
                root,
                "ownership-asus-nb-wmi.lock",
            ),
        )

    def dptc():
        return AmdDptcBackend(
            fallback,
            root=root,
            write_max=device.cooler_max,
            safety_lock_path=_runtime_lock_path(root, "firmware-amd-dptc.lock"),
            ownership_lock_path=_runtime_lock_path(root, "ownership-amd-dptc.lock"),
        )

    def msi_a8():
        return MsiClawA8FirmwareBackend(
            fallback,
            root=root,
            safety_lock_path=_runtime_lock_path(root, "firmware-msi-claw-a8.lock"),
            ownership_lock_path=_runtime_lock_path(root, "ownership-msi-claw-a8.lock"),
        )

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
    if os_id != "anatase":
        if key == "msi_claw_a8":
            return [ryzenadj]
        if key == "onexplayer_apex":
            return [alib, ryzenadj]
        if key in _RYZENADJ_ONLY_KEYS:
            return [asus, lenovo, msi, ryzenadj]
        if key.startswith("rog_"):
            return [asus, asus_nb_wmi, lenovo, msi, *amd_tail]
        if key.startswith("legion_"):
            return [lenovo, asus, msi, *amd_tail]
        return [asus, lenovo, msi, *amd_tail]

    if key == "msi_claw_a8":
        return [msi_a8, ryzenadj]
    if key == "onexplayer_apex":
        return [dptc, alib, ryzenadj]
    if key in _RYZENADJ_ONLY_KEYS:
        return [dptc, asus, lenovo, msi, ryzenadj]
    if key.startswith("rog_"):
        return [asus, asus_nb_wmi, *amd_tail]
    if key.startswith("legion_"):
        return [lenovo, asus, msi, *amd_tail]
    # generic / other AMD. intel-rapl excluded (AMD RAPL can confirm a write without
    # changing real TDP); deck excluded (steamdeck-hwmon matches any power*_cap chip,
    # incl. amdgpu's GPU cap — wrong rail).
    return [dptc, asus, lenovo, msi, *amd_tail]


def select_backend(device, root="/", ryzenadj_resolve=None, os_id=None) -> TDPBackend:
    """Pick the first supported TDP strategy for the detected device; else NullBackend."""
    fallback = TdpLimits.from_profile(device)

    def ryzenadj():
        kwargs = {"resolve": ryzenadj_resolve} if ryzenadj_resolve is not None else {}
        gpd_recovery = is_gpd_win_mini_2025_tdp_recovery(device, root)
        strict_readback = device.key in _STRICT_RYZENADJ_KEYS or (
            device.key == "gpd_win_mini_2025" and not gpd_recovery
        )
        return RyzenadjBackend(
            fallback,
            write_max=device.cooler_max,
            write_max_ac=(
                None if gpd_recovery else device.experimental_tdp_max_ac
            ),
            power_only_retry=gpd_recovery,
            require_readback=strict_readback,
            safety_lock_path=_runtime_lock_path(
                root,
                f"ryzenadj-{device.key}.lock",
            ),
            **kwargs,
        )

    trace = []
    for make in _candidates(device, fallback, root, ryzenadj, os_id):
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
        trace_item = {
            "candidate": candidate,
            "backend": backend.name,
            "supported": bool(backend.supported),
        }
        safety_locked = bool(getattr(backend, "safety_locked", False))
        ready = bool(backend.supported)
        if ready and not safety_locked:
            try:
                ready = bool(backend.selection_ready())
            except Exception as exc:  # noqa: BLE001
                ready = False
                trace_item["error"] = type(exc).__name__
        if backend.supported and not ready:
            trace_item["ready"] = False
            try:
                details = backend.selection_diagnostics()
            except Exception as exc:  # noqa: BLE001
                details = {}
                trace_item["diagnostics_error"] = type(exc).__name__
            if isinstance(details, dict):
                trace_item.update(details)
        trace.append(trace_item)
        if ready or safety_locked:
            backend.probe_trace = tuple(trace)
            return backend
    backend = NullBackend(f"no supported TDP interface for {device.key}")
    backend.probe_trace = tuple(trace)
    return backend


def select_low_battery_hold_backend(
    device,
    root="/",
    ryzenadj_resolve=None,
) -> RyzenadjBackend | None:
    if not is_legion_go_s_83n6(device, root):
        return None
    fallback = TdpLimits.from_profile(device)
    kwargs = {"resolve": ryzenadj_resolve} if ryzenadj_resolve is not None else {}
    backend = RyzenadjBackend(
        fallback,
        allow_unverified_hold=True,
        unverified_hold_restore={"pl1": 15, "pl2": 15, "pl3": 20},
        hold_rail_floors=legion_go_s_83n6_rail_floors(device, root),
        safety_lock_path=_runtime_lock_path(
            root,
            "low-battery-hold-legion-go-s-83n6.lock",
        ),
        **kwargs,
    )
    backend.name = "ryzenadj-low-battery-hold"
    backend.low_battery_hold_strategy = "legion-go-s-83n6"
    return backend
