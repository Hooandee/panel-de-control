import os

import armada_os

from device_quirks import (
    asus_tdp_authoritative_reassert_s,
    is_gpd_win_mini_2025_tdp_recovery,
    is_legion_go_s_83n6,
    is_msi_claw_8_ai_plus_a2vm,
    legion_go_2_83n0_firmware_attr_quirks,
    legion_go_s_83l3_firmware_attr_quirks,
    legion_go_s_83n6_firmware_attr_quirks,
    legion_go_s_83n6_boost_floors_menu_only,
    legion_go_s_83n6_rail_floors,
    lenovo_legion_firmware_attr_quirks,
)
from tdp.alib import AlibBackend
from tdp.amd_dptc import AmdDptcBackend
from tdp.arm_levels import ArmPerformanceLevels
from tdp.asus_nb_wmi import AsusNbWmiBackend
from tdp.backend import NullBackend, TDPBackend
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.intel_rapl import IntelRaplBackend, firmware_pl1_ceiling_w
from tdp.msi_claw_intel import MsiClawIntelBackend
from tdp.msi_claw_a8 import MsiClawA8FirmwareBackend
from tdp.routes import DEFAULT as DEFAULT_ROUTES, TdpRoutes
from tdp.runtime_lock import RuntimeSafetyLock
from tdp.ryzenadj import RyzenadjBackend
from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits
from tdp.write_ceilings import charger_cooler_max, charger_write_max, cooler_write_max


def _runtime_lock_path(root, name):
    return os.path.join(root, "run/panel-de-control", name)


def _not_honored_path(root, device_key, backend_name):
    safe = backend_name.replace(":", "-").replace("/", "-")
    return _runtime_lock_path(root, f"route-{safe}-{device_key}.not-honored")


_ROUTE_RETRIES_PER_BOOT = 2


def retry_degraded_routes(device, root="/") -> list[str]:
    """On plugin load, give routes this boot marked unreadable, failing or not honored
    another chance, at most a couple of times per boot so a broken route cannot flap."""
    run = _runtime_lock_path(root, "")
    suffix = f"-{device.key}"
    try:
        names = sorted(os.listdir(run))
    except OSError:
        return []
    markers = [
        name for name in names
        if name.endswith(
            (f"{suffix}.unreadable", f"{suffix}.not-honored", f"{suffix}.lock.failures")
        )
    ]
    if not markers:
        return []
    counter = RuntimeSafetyLock(os.path.join(run, f"route-retries{suffix}"))
    try:
        retries = int(counter.load() or 0)
    except ValueError:
        retries = 0
    if retries >= _ROUTE_RETRIES_PER_BOOT or not counter.persist(str(retries + 1)):
        return []
    cleared = []
    for name in markers:
        try:
            os.unlink(os.path.join(run, name))
            cleared.append(name)
        except OSError:
            pass
    return cleared


def mark_route_not_honored(device, backend_name, detail, root="/") -> bool:
    path = _not_honored_path(root, device.key, backend_name)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(str(detail)[:512])
        return True
    except OSError:
        return False


def _routes(device) -> TdpRoutes:
    return getattr(device, "tdp_routes", DEFAULT_ROUTES)


def _candidates(device, fallback, root, ryzenadj, os_id=None, desktop_cpu=False,
                ryzenadj_unverified=None):
    """Ordered probe chain of backend factories (constructed lazily by the caller,
    so an early match costs no extra sysfs work). The machine's route ladder lists its
    known-good interface first, then every other known path by capability, so a known
    device stays robust if a kernel update moves its interface and an unrecognised
    handheld still lands on whatever it actually exposes."""
    routes = _routes(device)
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
            trust_live_bounds=routes.asus_trust_live_bounds,
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-asus-armoury.lock",
            ),
            restore_on_release=os_id == "anatase",
            ownership_lock_path=_runtime_lock_path(
                root,
                "ownership-asus-armoury.lock",
            ),
            write_max_ac=charger_write_max(device),
        )

    def lenovo():
        go_s_83l3 = legion_go_s_83l3_firmware_attr_quirks(device, root)
        boost_floors = legion_go_s_83n6_rail_floors(device, root)
        floors_menu_only = legion_go_s_83n6_boost_floors_menu_only(device, root)
        backend = FirmwareAttrBackend(
            "lenovo-wmi-other",
            fallback,
            root=root,
            profile_name="lenovo-wmi-gamezone",
            is_generic=generic,
            rail_floors=None if floors_menu_only else boost_floors,
            menu_rail_floors=boost_floors if floors_menu_only else None,
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-lenovo-wmi-other.lock",
            ),
            write_max_ac=charger_write_max(device),
            **lenovo_legion_firmware_attr_quirks(device, root),
            **legion_go_2_83n0_firmware_attr_quirks(device, root),
            **go_s_83l3,
            **legion_go_s_83n6_firmware_attr_quirks(device, root),
        )
        if go_s_83l3:
            backend.low_battery_hold_strategy = None
        return backend

    def msi():
        manual = FirmwareAttrBackend(
            "msi-wmi-platform",
            fallback,
            root=root,
            is_generic=generic,
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-msi-wmi-platform.lock",
            ),
            write_max_ac=charger_write_max(device),
        )
        if not is_msi_claw_8_ai_plus_a2vm(device, root) or not manual.supported:
            return manual
        auto_firmware = FirmwareAttrBackend(
            "msi-wmi-platform",
            fallback,
            root=root,
            is_generic=generic,
            optional_rails=("pl3",),
            safety_lock_path=_runtime_lock_path(
                root,
                "firmware-msi-wmi-platform-auto.lock",
            ),
            restore_on_release=True,
            ownership_lock_path=_runtime_lock_path(
                root,
                "ownership-firmware-msi-wmi-platform.lock",
            ),
        )
        return MsiClawIntelBackend(manual, auto_firmware, intel())

    def intel():
        return IntelRaplBackend(
            fallback,
            root=root,
            safety_lock_path=_runtime_lock_path(
                root,
                "intel-rapl-transaction.lock",
            ),
            ownership_lock_path=_runtime_lock_path(
                root,
                "ownership-intel-rapl.lock",
            ),
            auto_tdp_allowed=is_msi_claw_8_ai_plus_a2vm(device, root),
            write_max_ac=device.experimental_tdp_max_ac,
            sync_surfaces=routes.rapl_sync_surfaces,
        )

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
            write_max_ac=charger_write_max(device),
        )

    def dptc():
        return AmdDptcBackend(
            fallback,
            root=root,
            write_max=cooler_write_max(device),
            write_max_ac=charger_write_max(device),
            rail_max_ac=charger_cooler_max(device),
            safety_lock_path=_runtime_lock_path(root, "firmware-amd-dptc.lock"),
            ownership_lock_path=_runtime_lock_path(root, "ownership-amd-dptc.lock"),
        )

    def msi_a8():
        return MsiClawA8FirmwareBackend(
            fallback,
            root=root,
            safety_lock_path=_runtime_lock_path(root, "firmware-msi-claw-a8.lock"),
            ownership_lock_path=_runtime_lock_path(root, "ownership-msi-claw-a8.lock"),
            write_max_ac=charger_write_max(device),
        )

    def arm_levels():
        on_release = armada_os.reload_powerd if armada_os.powerd_present(root) else None
        return ArmPerformanceLevels(root=root, on_release=on_release)

    def alib():
        return AlibBackend(fallback, root=root,
                           write_max=cooler_write_max(device),
                           write_max_ac=charger_write_max(device))

    builders = {
        "asus": asus,
        "asus_nb_wmi": asus_nb_wmi,
        "lenovo": lenovo,
        "msi": msi,
        "msi_a8": msi_a8,
        "dptc": dptc,
        "deck": deck,
        "intel": intel,
        "arm_levels": arm_levels,
        "ryzenadj": ryzenadj,
        "ryzenadj_unverified": ryzenadj_unverified,
        "alib": alib,
    }
    if routes.requires_firmware_ceiling and not desktop_cpu:
        return []
    chain = routes.chain(
        arch=getattr(device, "arch", "x86"),
        vendor=device.vendor,
        os_id=os_id,
    )
    return [builders[name] for name in chain]


_DESKTOP_MIN_W = 15


def _desktop_limits(device, root, hint_w=None) -> TdpLimits | None:
    if not _routes(device).requires_firmware_ceiling or device.vendor != "intel":
        return None
    ceiling = firmware_pl1_ceiling_w(root, hint_w)
    if ceiling is None:
        return None
    return TdpLimits(min(_DESKTOP_MIN_W, ceiling), ceiling, ceiling, ceiling)


def select_backend(device, root="/", ryzenadj_resolve=None, os_id=None,
                   desktop_ceiling_hint_w=None) -> TDPBackend:
    """Pick the first supported TDP strategy for the detected device; else NullBackend.
    A desktop CPU is only driven when its firmware PL1 ceiling is readable."""
    desktop_limits = _desktop_limits(device, root, desktop_ceiling_hint_w)
    fallback = desktop_limits or TdpLimits.from_profile(device)

    routes = _routes(device)

    def ryzenadj():
        kwargs = {"resolve": ryzenadj_resolve} if ryzenadj_resolve is not None else {}
        gpd_recovery = is_gpd_win_mini_2025_tdp_recovery(device, root)
        return RyzenadjBackend(
            fallback,
            write_max=cooler_write_max(device),
            write_max_ac=(
                None if gpd_recovery else charger_write_max(device)
            ),
            power_only_retry=gpd_recovery,
            require_readback=routes.ryzenadj == "strict" and not gpd_recovery,
            readback_fallback=routes.ryzenadj_readback_fallback,
            lock_experimental=bool(getattr(device, "experimental_tdp_max_ac", None)),
            safety_lock_path=_runtime_lock_path(
                root,
                f"ryzenadj-{device.key}.lock",
            ),
            unreadable_marker_path=(
                _runtime_lock_path(root, f"ryzenadj-{device.key}.unreadable")
                if routes.ryzenadj_yields_when_unreadable
                else None
            ),
            **kwargs,
        )

    def ryzenadj_unverified():
        kwargs = {"resolve": ryzenadj_resolve} if ryzenadj_resolve is not None else {}
        return RyzenadjBackend(
            fallback,
            write_max=fallback.max_w,
            write_max_ac=fallback.max_ac_w,
            write_temp_limit=False,
            safety_lock_path=_runtime_lock_path(
                root,
                f"ryzenadj-unverified-{device.key}.lock",
            ),
            measured_only=True,
            **kwargs,
        )

    trace = []
    not_honored_fallback = None
    for make in _candidates(device, fallback, root, ryzenadj, os_id,
                            desktop_cpu=desktop_limits is not None,
                            ryzenadj_unverified=ryzenadj_unverified):
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
        if backend.supported and os.path.exists(
            _not_honored_path(root, device.key, backend.name)
        ):
            trace_item["ready"] = False
            trace_item["not_honored_this_boot"] = True
            trace.append(trace_item)
            if not_honored_fallback is None:
                not_honored_fallback = backend
            continue
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
        blocks_fallback = bool(getattr(backend, "blocks_fallback", False))
        if ready or safety_locked or (backend.supported and blocks_fallback):
            backend.probe_trace = tuple(trace)
            return backend
    if not_honored_fallback is not None:
        not_honored_fallback.measured_not_honored = True
        not_honored_fallback.probe_trace = tuple(trace)
        return not_honored_fallback
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
