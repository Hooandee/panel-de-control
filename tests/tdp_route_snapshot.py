"""Deterministic record of what the TDP factory selects and writes for every machine, OS and
interface state. The pinned record keeps route selection identical across refactors."""
import hashlib
import json
import os
import subprocess
import tempfile
from unittest import mock

from device_profiles import ARM_DEVICE_TABLE, DESKTOP_PC, DEVICE_TABLE, GENERIC, GENERIC_ARM
from tdp import alib
from tdp.factory import select_backend
from tdp.ryzenadj import RyzenadjBackend

_OS_IDS = (None, "anatase")
_RYZENADJ_MODES = ("absent", "three_rail", "stapm_only", "unreadable")
_CAPABILITY_ATTRS = (
    "supported", "readback", "auto_tdp_supported", "auto_tdp_safe", "measured_verification",
    "measured_not_honored", "supports_levels", "blocking", "guard_interval_s", "heartbeat_s",
    "authoritative_reassert_s", "low_battery_hold_strategy", "reselection_safe_after_use",
    "primary_rail", "manual_write_max_ac", "safety_locked", "blocks_fallback", "read_tolerance_w",
    "unit",
)

_MACHINE_DMI = {
    "gpd_win_mini_2025": (("gpd", "G1617-02", ""), ("gpd", "G1617-01", "")),
    "msi_claw_8_ai_plus": (("Micro-Star International Co., Ltd.", "Claw 8 AI+ A2VM", ""),),
    "rog_xbox_ally_x": (("ASUSTeK COMPUTER INC.", "ROG Xbox Ally X RC73XA_RC73XA", ""),),
    "legion_go": (("LENOVO", "83E1", ""),),
    "legion_go_s": (("LENOVO", "83N6", "S0CN27WW"), ("LENOVO", "83N6", "S0CN30WW"),
                    ("LENOVO", "83L3", "QCCN16WW")),
    "legion_go_2": (("LENOVO", "83N0", ""), ("LENOVO", "83N1", "")),
}


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _firmware(root, provider, readable=True):
    base = os.path.join(root, "sys/class/firmware-attributes", provider, "attributes")
    for attr, maximum in (("ppt_pl1_spl", 35), ("ppt_pl2_sppt", 45), ("ppt_pl3_fppt", 55)):
        path = os.path.join(base, attr)
        for leaf, value in (("current_value", 15), ("min_value", 5), ("max_value", maximum)):
            _write(os.path.join(path, leaf), value if readable else "")


def _platform_profile(root, name):
    base = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    _write(os.path.join(base, "name"), name)
    _write(os.path.join(base, "profile"), "balanced")
    _write(os.path.join(base, "choices"), "low-power balanced performance custom")


def _asus_legacy(root):
    base = os.path.join(root, "sys/devices/platform/asus-nb-wmi")
    for leaf, value in (("ppt_pl1_spl", 15), ("ppt_pl2_sppt", 20), ("ppt_fppt", 25)):
        _write(os.path.join(base, leaf), value)


def _deck_hwmon(root):
    base = os.path.join(root, "sys/class/hwmon/hwmon0")
    _write(os.path.join(base, "name"), "amdgpu")
    for index, label, watts in ((1, "slowPPT", 15), (2, "fastPPT", 15)):
        _write(os.path.join(base, f"power{index}_cap"), watts * 1_000_000)
        _write(os.path.join(base, f"power{index}_label"), label)


def _rapl(root):
    base = os.path.join(root, "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0")
    _write(os.path.join(base, "name"), "package-0")
    for index, name, microwatts in ((0, "long_term", 30_000_000), (1, "short_term", 37_000_000)):
        _write(os.path.join(base, f"constraint_{index}_name"), name)
        _write(os.path.join(base, f"constraint_{index}_power_limit_uw"), microwatts)


def _acpi_call(root):
    _write(os.path.join(root, "proc/acpi/call"), "not called")


ENVIRONMENTS = {
    "bare": (),
    "asus_armoury": (lambda r: _firmware(r, "asus-armoury"),),
    "asus_armoury_unreadable+legacy": (
        lambda r: _firmware(r, "asus-armoury", readable=False), _asus_legacy),
    "asus_legacy": (_asus_legacy,),
    "lenovo": (lambda r: _firmware(r, "lenovo-wmi-other"),
               lambda r: _platform_profile(r, "lenovo-wmi-gamezone")),
    "msi": (lambda r: _firmware(r, "msi-wmi-platform"),),
    "dptc": (lambda r: _firmware(r, "amd-dptc"), lambda r: _platform_profile(r, "amd-dptc")),
    "deck_hwmon": (_deck_hwmon,),
    "rapl": (_rapl,),
    "acpi_call": (_acpi_call,),
}


class _FakeRyzenadj:
    """In-process ryzenadj: `-i` reports the last written limits, writes are logged."""

    def __init__(self, mode):
        self.mode = mode
        self.limits = {"--stapm-limit": 15000, "--fast-limit": 15000, "--slow-limit": 15000}
        self.writes = []

    def __call__(self, argv, **_kwargs):
        args = list(argv[1:])
        if args[:1] == ["-i"]:
            if self.mode == "unreadable":
                return subprocess.CompletedProcess(argv, 251, "", "Unable to get memory access\n")
            lines = [f"| STAPM LIMIT | {self.limits['--stapm-limit'] / 1000:.3f} | stapm-limit |"]
            if self.mode == "three_rail":
                lines += [
                    f"| PPT LIMIT FAST | {self.limits['--fast-limit'] / 1000:.3f} | fast-limit |",
                    f"| PPT LIMIT SLOW | {self.limits['--slow-limit'] / 1000:.3f} | slow-limit |",
                ]
            return subprocess.CompletedProcess(argv, 0, "\n".join(lines) + "\n", "")
        self.writes.append(" ".join(args))
        for flag, value in zip(args[::2], args[1::2]):
            if flag in self.limits:
                self.limits[flag] = int(value)
        return subprocess.CompletedProcess(argv, 0, "", "")


def _no_modprobe(argv, **_kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "")


def _dmi(root, vendor, product, bios):
    base = os.path.join(root, "sys/class/dmi/id")
    _write(os.path.join(base, "sys_vendor"), vendor)
    _write(os.path.join(base, "product_name"), product)
    _write(os.path.join(base, "bios_version"), bios)


def _sanitize(value, root):
    if isinstance(value, dict):
        return {str(k): _sanitize(v, root) for k, v in sorted(value.items(), key=lambda i: str(i[0]))}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, root) for v in value]
    if isinstance(value, str):
        return value.replace(root, "<root>")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return repr(value).replace(root, "<root>")


def _sysfs_state(root):
    state = {}
    for base, _dirs, files in os.walk(os.path.join(root, "sys")):
        for name in files:
            path = os.path.join(base, name)
            if name in ("current_value", "profile") or "power_limit_uw" in name or (
                "ppt_" in name and "asus-nb-wmi" in path
            ) or name.endswith("_cap"):
                with open(path) as handle:
                    state[os.path.relpath(path, root)] = handle.read().strip()
    return state


def _result(result):
    return {
        "requested": getattr(result, "requested_w", None),
        "applied": getattr(result, "applied_w", None),
        "ok": getattr(result, "ok", None),
        "detail": getattr(result, "detail", None),
        "failure_kind": getattr(result, "failure_kind", None),
    }


def _call(fn, *args):
    try:
        return fn(*args)
    except Exception as error:  # noqa: BLE001
        return f"raised {type(error).__name__}"


def _with_runner(runner):
    defaults = list(RyzenadjBackend.__init__.__defaults__)
    defaults[1] = runner
    return mock.patch.object(RyzenadjBackend.__init__, "__defaults__", tuple(defaults))


def record(device, os_id, environment, ryzenadj_mode, dmi=None):
    fake = _FakeRyzenadj(ryzenadj_mode)
    with mock.patch("time.sleep"), _with_runner(fake), \
            mock.patch.object(alib.subprocess, "run", _no_modprobe), \
            tempfile.TemporaryDirectory() as root:
        if dmi is not None:
            _dmi(root, *dmi)
        for build in ENVIRONMENTS[environment]:
            build(root)
        resolve = (lambda: None) if ryzenadj_mode == "absent" else (lambda: "/opt/fake/ryzenadj")
        backend = select_backend(device, root=root, ryzenadj_resolve=resolve, os_id=os_id)
        selected = {
            "backend": backend.name,
            "class": type(backend).__name__,
            "trace": list(getattr(backend, "probe_trace", ())),
            "capabilities": {
                attr: getattr(backend, attr) for attr in _CAPABILITY_ATTRS if hasattr(backend, attr)
            },
            "limits": _call(lambda: vars(backend.get_limits())),
        }
        script = {}
        probe = getattr(backend, "probe", None)
        script["probe"] = _call(probe) if callable(probe) else None
        script["set_15_dc"] = _call(lambda: _result(backend.set_tdp(15, False)))
        script["set_8_ac"] = _call(lambda: _result(backend.set_tdp(8, True)))
        script["levels_12_15_20_ac"] = _call(
            lambda: _result(backend.set_levels(12, 15, 20, True))
        )
        script["after_writes"] = {
            attr: getattr(backend, attr) for attr in _CAPABILITY_ATTRS if hasattr(backend, attr)
        }
        diagnostics = getattr(backend, "diagnostics", None)
        script["diagnostics"] = _call(diagnostics) if callable(diagnostics) else None
        script["release"] = _call(backend.release)
        script["ryzenadj_writes"] = list(fake.writes)
        script["sysfs"] = _sysfs_state(root)
        run = os.path.join(root, "run/panel-de-control")
        script["run_markers"] = sorted(os.listdir(run)) if os.path.isdir(run) else []
        return _sanitize({"selected": selected, "script": script}, root)


def scenarios():
    devices = [*DEVICE_TABLE, GENERIC, DESKTOP_PC, GENERIC_ARM, *ARM_DEVICE_TABLE]
    for device in devices:
        dmis = _MACHINE_DMI.get(device.key, (None,))
        for dmi in dmis:
            for os_id in _OS_IDS:
                for environment in ENVIRONMENTS:
                    modes = _RYZENADJ_MODES if environment in (
                        "bare", "asus_armoury_unreadable+legacy", "acpi_call",
                    ) else ("absent", "three_rail")
                    for mode in modes:
                        dmi_id = dmi[1] + (f"/{dmi[2]}" if dmi and dmi[2] else "") if dmi else "-"
                        yield (
                            f"{device.key}|{dmi_id}|{os_id or 'other'}|{environment}|{mode}",
                            (device, os_id, environment, mode, dmi),
                        )


def digest(entry):
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_snapshot():
    return {name: record(*args) for name, args in scenarios()}


def build_digests():
    return {name: digest(record(*args)) for name, args in scenarios()}


if __name__ == "__main__":
    import sys

    target, *mode = sys.argv[1:]
    data = build_snapshot() if mode == ["--full"] else build_digests()
    with open(target, "w") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")
