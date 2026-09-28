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
    assert settings["_desktop_pc_seeded"] is True
    assert settings["_desktop_pc_prev_tdp_control"] is True

    settings["desktop_power_mode"] = "balanced"
    assert migrate_desktop_defaults(settings, DESKTOP_PC) is False
    assert settings["desktop_power_mode"] == "balanced"


def test_misdetected_handheld_gets_its_tdp_switch_back():
    from desktop.mode import migrate_desktop_defaults
    from device_profiles import GENERIC
    settings = {"tdp_control_enabled": True}
    migrate_desktop_defaults(settings, DESKTOP_PC)

    assert migrate_desktop_defaults(settings, GENERIC) is True
    assert settings["tdp_control_enabled"] is True
    assert settings["_desktop_pc_seeded"] is False


def test_desktop_seed_survives_a_real_settings_round_trip(tmp_path):
    import sys
    import types
    if "decky" not in sys.modules:
        decky = types.ModuleType("decky")
        decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
        decky.DECKY_USER_HOME = "/tmp"
        decky.DECKY_USER = "deck"
        decky.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                             warning=lambda *a, **k: None,
                                             error=lambda *a, **k: None)
        sys.modules["decky"] = decky
    from main import DEFAULTS
    from desktop.mode import migrate_desktop_defaults
    from device_profiles import GENERIC
    from settings_store import SettingsStore
    store = SettingsStore(str(tmp_path / "settings.json"))

    settings = store.load(DEFAULTS)
    migrate_desktop_defaults(settings, DESKTOP_PC)
    settings["desktop_power_mode"] = "balanced"
    store.save(settings)

    settings = store.load(DEFAULTS)
    assert migrate_desktop_defaults(settings, DESKTOP_PC) is False
    assert settings["desktop_power_mode"] == "balanced"
    store.save(settings)

    settings = store.load(DEFAULTS)
    assert migrate_desktop_defaults(settings, GENERIC) is True
    assert settings["tdp_control_enabled"] is True


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


def test_onexplayer_3_rapl_write_reaches_45_w_only_on_ac(tmp_path):
    from device_profiles import DEVICE_TABLE
    rapl = _rapl(str(tmp_path), pl1_w=25)
    oxp3 = next(p for p in DEVICE_TABLE if p.key == "onexplayer_3")
    backend = select_backend(oxp3, root=str(tmp_path))
    path = os.path.join(rapl, "constraint_0_power_limit_uw")

    assert backend.get_limits().max_ac_w == 35
    backend.set_tdp(60, True)
    with open(path) as handle:
        assert int(handle.read()) == 45_000_000
    backend.set_tdp(60, False)
    with open(path) as handle:
        assert int(handle.read()) == 35_000_000


def test_free_restores_an_unlimited_firmware_pl1_verbatim(tmp_path):
    from desktop.power import DesktopPowerCoordinator

    class NoGpu:
        supported = False

        def state(self):
            return {"supported": False, "current_w": None, "min_w": None,
                    "max_w": None, "default_w": None}

    rapl = _rapl(str(tmp_path), pl1_w=1, max_w=125)
    limit = os.path.join(rapl, "constraint_0_power_limit_uw")
    _w(limit, "4095875000")
    cpu = select_backend(dataclasses.replace(DESKTOP_PC, vendor="intel"), root=str(tmp_path))
    assert cpu.get_limits().max_ac_w == 125
    coordinator = DesktopPowerCoordinator(cpu, NoGpu(), persist_state=lambda _s: None,
                                          boot_id="boot", device_key="desktop_pc",
                                          firmware_relative=True)

    assert coordinator.apply("performance")["ok"] is True
    with open(limit) as handle:
        assert int(handle.read()) == 125_000_000
    assert coordinator.apply("free")["ok"] is True
    with open(limit) as handle:
        assert handle.read() == "4095875000"


def test_intel_desktop_without_a_readable_ceiling_is_not_driven(tmp_path):
    d = os.path.join(str(tmp_path), "sys/devices/virtual/powercap/intel-rapl/intel-rapl:0")
    _w(os.path.join(d, "name"), "package-0")
    _w(os.path.join(d, "constraint_0_power_limit_uw"), "4095875000")
    device = dataclasses.replace(DESKTOP_PC, vendor="intel")
    assert isinstance(select_backend(device, root=str(tmp_path)), NullBackend)


def test_same_boot_handoff_keeps_the_firmware_ceiling_after_a_restart(tmp_path):
    from desktop.power import handoff_cpu_ceiling_w
    _rapl(str(tmp_path), pl1_w=62)
    state = {"version": 1, "boot_id": "b1", "device_key": "desktop_pc",
             "baseline": {"cpu_w": 125, "cpu_uw": {"intel-rapl:0": 125_000_000},
                          "cpu_policy": None, "gpu_uw": None}}
    hint = handoff_cpu_ceiling_w(state, boot_id="b1")
    backend = select_backend(dataclasses.replace(DESKTOP_PC, vendor="intel"),
                             root=str(tmp_path), desktop_ceiling_hint_w=hint)

    assert backend.get_limits().max_ac_w == 125
    assert handoff_cpu_ceiling_w(state, boot_id="b2") is None


def test_x2_mini_pro_cooler_ceiling_is_charger_only_and_skips_presets(tmp_path):
    import sys
    import types
    from device_profiles import DEVICE_TABLE
    from tdp.types import TdpLimits
    if "decky" not in sys.modules:
        decky = types.ModuleType("decky")
        decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
        decky.DECKY_USER_HOME = "/tmp"
        decky.DECKY_USER = "deck"
        decky.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                             warning=lambda *a, **k: None,
                                             error=lambda *a, **k: None)
        sys.modules["decky"] = decky
    import main
    x2 = next(p for p in DEVICE_TABLE if p.key == "onexplayer_x2_mini_pro")

    backend = select_backend(x2, root=str(tmp_path), ryzenadj_resolve=lambda: "/bin/ryzenadj")
    assert backend.name == "ryzenadj"
    assert (backend._write_limits.max_w, backend._write_limits.max_ac_w) == (55, 120)

    plugin = main.Plugin.__new__(main.Plugin)
    plugin._device = x2
    plugin._settings = {"cooler_boost": True}
    plugin._tdp_backend = types.SimpleNamespace(get_limits=lambda: TdpLimits.from_profile(x2))
    plugin._steamdeck_overclock_state = lambda: {"max_w": None}

    limits = plugin._limits()
    assert (limits.max_w, limits.max_ac_w) == (55, 120)
    automatic = plugin._automatic_limits(limits)
    assert (automatic.max_w, automatic.max_ac_w) == (55, 80)


def test_oxp3_writes_and_verifies_both_rapl_surfaces(tmp_path):
    from device_profiles import DEVICE_TABLE
    msr = _rapl(str(tmp_path), pl1_w=25)
    mmio = os.path.join(str(tmp_path), "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0")
    _w(os.path.join(mmio, "name"), "package-0")
    _w(os.path.join(mmio, "constraint_0_power_limit_uw"), "15000000")
    oxp3 = next(p for p in DEVICE_TABLE if p.key == "onexplayer_3")
    backend = select_backend(oxp3, root=str(tmp_path))

    assert backend.read_applied() == 15
    assert backend.set_tdp(30, True).ok is True
    for surface in (msr, mmio):
        with open(os.path.join(surface, "constraint_0_power_limit_uw")) as handle:
            assert int(handle.read()) == 30_000_000


def test_desktop_ceiling_is_the_lowest_active_surface(tmp_path):
    from tdp.intel_rapl import firmware_pl1_ceiling_w
    _rapl(str(tmp_path), pl1_w=65, max_w=125)
    mmio = os.path.join(str(tmp_path), "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0")
    _w(os.path.join(mmio, "constraint_0_power_limit_uw"), "4095875000")
    assert firmware_pl1_ceiling_w(str(tmp_path)) == 65
