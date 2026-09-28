import dataclasses
import os

from device_profiles import DESKTOP_PC
from tdp.backend import NullBackend
from tdp.factory import select_backend
from tdp.intel_rapl import IntelRaplBackend


def _w(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(value)


def _rapl(root, pl1_w, max_w=None):
    d = os.path.join(root, "sys/devices/virtual/powercap/intel-rapl/intel-rapl:0")
    _w(os.path.join(d, "name"), "package-0")
    _w(os.path.join(d, "constraint_0_name"), "long_term")
    _w(os.path.join(d, "constraint_0_power_limit_uw"), str(pl1_w * 1_000_000))
    _w(os.path.join(d, "constraint_1_name"), "short_term")
    _w(os.path.join(d, "constraint_1_power_limit_uw"), str(2 * pl1_w * 1_000_000))
    if max_w is not None:
        _w(os.path.join(d, "constraint_0_max_power_uw"), str(max_w * 1_000_000))
    return d


def test_intel_desktop_cpu_range_is_bounded_by_the_firmware_pl1(tmp_path):
    rapl = _rapl(str(tmp_path), pl1_w=95, max_w=65)
    device = dataclasses.replace(DESKTOP_PC, vendor="intel")

    backend = select_backend(device, root=str(tmp_path))

    assert isinstance(backend, IntelRaplBackend)
    limits = backend.get_limits()
    assert (limits.min_w, limits.max_w, limits.max_ac_w) == (15, 95, 95)
    backend.set_tdp(200, True)
    with open(os.path.join(rapl, "constraint_0_power_limit_uw")) as handle:
        assert int(handle.read()) == 95_000_000


def test_amd_desktop_cpu_has_no_power_backend(tmp_path):
    _rapl(str(tmp_path), pl1_w=76)
    device = dataclasses.replace(DESKTOP_PC, vendor="amd")
    assert isinstance(select_backend(device, root=str(tmp_path)), NullBackend)


def test_intel_desktop_without_rapl_is_null(tmp_path):
    device = dataclasses.replace(DESKTOP_PC, vendor="intel")
    assert isinstance(select_backend(device, root=str(tmp_path)), NullBackend)


class _Cpu:
    supported = True

    def __init__(self, ceiling):
        from tdp.types import TdpLimits
        self.limits = TdpLimits(15, ceiling, ceiling, ceiling)
        self.writes = []

    def get_limits(self):
        return self.limits

    def read_applied(self):
        return self.writes[-1] if self.writes else self.limits.max_w

    def set_tdp(self, watts, ac):
        from tdp.types import TdpResult
        target = self.limits.clamp(watts, ac)
        self.writes.append(target)
        return TdpResult(target, target, True, "")


class _Gpu:
    supported = True

    def __init__(self):
        self.writes = []

    def state(self):
        return {"supported": True, "current_w": 263, "min_w": 200,
                "max_w": 300, "default_w": 263}

    def capture(self):
        return 263_000_000

    def set_watts(self, watts):
        self.writes.append(watts)
        return {"ok": True, "applied_w": watts, "requested_w": watts, "detail": "applied"}

    def restore(self, target_uw=None):
        return {"ok": True, "applied_w": 263, "detail": "restored"}


def _coordinator(cpu, gpu):
    from desktop.power import DesktopPowerCoordinator
    return DesktopPowerCoordinator(cpu, gpu, persist_state=lambda _s: None,
                                   boot_id="boot", device_key="desktop_pc",
                                   firmware_relative=True)


def test_desktop_presets_scale_from_firmware_limits_never_above_them():
    cpu, gpu = _Cpu(ceiling=125), _Gpu()
    coordinator = _coordinator(cpu, gpu)

    state = coordinator.state()
    assert (state["cpu_min_w"], state["cpu_max_w"]) == (15, 125)
    assert {k: (v["cpu_w"], v["gpu_w"]) for k, v in state["presets"].items()} == {
        "silent": (62, 200), "balanced": (94, 232), "performance": (125, 263)}

    assert coordinator.apply("performance")["ok"] is True
    assert (cpu.writes, gpu.writes) == ([125], [263])
    assert coordinator.apply_custom(400, 999)["ok"] is True
    assert (cpu.writes[-1], gpu.writes[-1]) == (125, 300)


def test_steam_machine_presets_keep_their_validated_watts():
    from desktop.power import DesktopPowerCoordinator, PRESETS
    coordinator = DesktopPowerCoordinator(_Cpu(30), _Gpu(), boot_id="boot",
                                          device_key="steam_machine")
    assert {k: (v["cpu_w"], v["gpu_w"]) for k, v in coordinator.state()["presets"].items()} \
        == PRESETS


def test_desktop_pc_seeds_pass_through_once_and_disables_handheld_tdp():
    from desktop.mode import migrate_desktop_defaults
    settings = {"tdp_control_enabled": True, "desktop_mode_enabled": True,
                "desktop_prev_tdp_control": True, "desktop_power_mode": "silent"}

    assert migrate_desktop_defaults(settings, DESKTOP_PC) is True
    assert settings["tdp_control_enabled"] is False
    assert settings["desktop_power_mode"] == "free"
    assert settings["desktop_mode_enabled"] is False
    assert settings["_desktop_defaults_migrated"] is True

    settings["desktop_power_mode"] = "balanced"
    assert migrate_desktop_defaults(settings, DESKTOP_PC) is False
    assert settings["desktop_power_mode"] == "balanced"


def test_desktop_gpu_power_cap_uses_the_driver_bounds(tmp_path):
    from gpu.power_cap import AmdGpuPowerCap
    root = str(tmp_path)
    card = os.path.join(root, "sys/devices/pci0000:00/0000:03:00.0")
    hwmon = os.path.join(card, "hwmon/hwmon2")
    for leaf, value in (("name", "amdgpu"), ("power1_cap", "263000000"),
                        ("power1_cap_min", "200000000"), ("power1_cap_max", "300000000"),
                        ("power1_cap_default", "263000000")):
        _w(os.path.join(hwmon, leaf), value)
    os.makedirs(os.path.join(root, "sys/class/hwmon"))
    os.symlink(hwmon, os.path.join(root, "sys/class/hwmon/hwmon2"))
    os.symlink(card, os.path.join(hwmon, "device"))
    os.makedirs(os.path.join(root, "sys/class/drm/card1"))
    os.symlink(card, os.path.join(root, "sys/class/drm/card1/device"))

    cap = AmdGpuPowerCap(root=root, device_key="desktop_pc")

    assert cap.state()["max_w"] == 300
    assert cap.set_watts(999)["applied_w"] == 300
    assert cap.restore()["ok"] is True
    with open(os.path.join(hwmon, "power1_cap")) as handle:
        assert handle.read() == "263000000"
