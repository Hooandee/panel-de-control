import asyncio
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

import main
from desktop.fan_store import DesktopFanStore
from device_registry import detect


class Coordinator:
    def __init__(self):
        self.mode = "free"
        self.calls = []

    def state(self):
        return {"supported": True, "cpu_supported": True, "gpu_supported": True,
                "mode": self.mode, "cpu_w": 30, "gpu_w": 110,
                "cpu_min_w": 4, "cpu_max_w": 30, "gpu_min_w": 55, "gpu_max_w": 110,
                "presets": {}}

    def apply(self, mode):
        self.calls.append(("mode", mode))
        self.mode = mode
        return {"ok": True, "mode": mode, "cpu_w": 23, "gpu_w": 80, "detail": "applied"}

    def apply_custom(self, cpu, gpu):
        self.calls.append(("custom", cpu, gpu))
        self.mode = "custom"
        return {"ok": True, "mode": "custom", "cpu_w": cpu, "gpu_w": gpu, "detail": "applied"}

    def restore(self):
        self.calls.append(("restore",))
        self.mode = "free"
        return {"ok": True, "mode": "free", "cpu_w": 30, "gpu_w": 110, "detail": "restored"}


def _plugin(device="Fremont", manual=False):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._device = detect(product_name=device)
    plugin._settings = {"desktop_mode_enabled": manual, "desktop_power_mode": "free",
                        "desktop_cpu_w": 23, "desktop_gpu_w": 80,
                        "tdp_control_enabled": False, "desktop_prev_tdp_control": None}
    plugin._desktop_power = Coordinator()
    plugin._save = lambda: None
    plugin._advance_tdp_generation = lambda: None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    return plugin


def test_fremont_rpc_reports_automatic_desktop_mode():
    state = asyncio.run(_plugin().get_desktop_state())
    assert state["enabled"] is True
    assert state["automatic"] is True
    assert state["power"]["mode"] == "free"


def test_generic_rpc_is_disabled_until_manual_opt_in():
    assert asyncio.run(_plugin("Unknown PC").get_desktop_state())["enabled"] is False
    assert asyncio.run(_plugin("Unknown PC", manual=True).get_desktop_state())["enabled"] is True


def test_selecting_profile_persists_only_after_success():
    plugin = _plugin()
    result = asyncio.run(plugin.set_desktop_power_mode("balanced"))
    assert result["ok"] is True
    assert plugin._settings["desktop_power_mode"] == "balanced"
    assert plugin._desktop_power.calls == [("mode", "balanced")]


def test_persisted_profile_never_overrides_the_coordinator_actual_mode():
    plugin = _plugin()
    plugin._settings["desktop_power_mode"] = "performance"
    plugin._desktop_power.mode = "free"

    state = asyncio.run(plugin.get_desktop_state())

    assert state["power"]["mode"] == "free"


def test_custom_power_persists_independent_cpu_and_gpu_values():
    plugin = _plugin()
    result = asyncio.run(plugin.set_desktop_power_limits(19, 72))
    assert result["ok"] is True
    assert plugin._settings["desktop_cpu_w"] == 19
    assert plugin._settings["desktop_gpu_w"] == 72
    assert plugin._settings["desktop_power_mode"] == "custom"


def test_gpu_only_custom_power_does_not_cast_unavailable_cpu_watts():
    plugin = _plugin()

    def gpu_only(cpu, gpu):
        return {"ok": True, "mode": "custom", "cpu_w": None,
                "gpu_w": gpu, "detail": "GPU only"}

    plugin._desktop_power.apply_custom = gpu_only
    result = asyncio.run(plugin.set_desktop_power_limits(23, 72))
    assert result["ok"] is True
    assert plugin._settings["desktop_cpu_w"] == 23
    assert plugin._settings["desktop_gpu_w"] == 72


def test_disabling_generic_desktop_restores_power_first():
    plugin = _plugin("Unknown PC", manual=True)
    state = asyncio.run(plugin.set_desktop_mode_enabled(False))
    assert plugin._desktop_power.calls[0] == ("restore",)
    assert state["enabled"] is False


def test_enabling_generic_desktop_releases_tdp_through_the_handoff_path():
    plugin = _plugin("Unknown PC")
    plugin._settings["tdp_control_enabled"] = True
    calls = []

    async def set_tdp(enabled):
        calls.append(enabled)
        plugin._settings["tdp_control_enabled"] = enabled
        return enabled

    plugin.set_tdp_control_enabled = set_tdp
    state = asyncio.run(plugin.set_desktop_mode_enabled(True))

    assert calls == [False]
    assert plugin._settings["desktop_prev_tdp_control"] is True
    assert state["enabled"] is True


def test_disabling_generic_desktop_restores_previous_tdp_through_apply_path():
    plugin = _plugin("Unknown PC", manual=True)
    plugin._settings["desktop_prev_tdp_control"] = True
    calls = []

    async def set_tdp(enabled):
        calls.append((enabled, list(plugin._desktop_power.calls)))
        plugin._settings["tdp_control_enabled"] = enabled
        return enabled

    plugin.set_tdp_control_enabled = set_tdp
    state = asyncio.run(plugin.set_desktop_mode_enabled(False))

    assert calls == [(True, [("restore",)])]
    assert plugin._settings["desktop_prev_tdp_control"] is None
    assert state["enabled"] is False


def test_failed_desktop_restore_keeps_mode_enabled_and_handheld_tdp_released():
    plugin = _plugin("Unknown PC", manual=True)
    plugin._settings["desktop_prev_tdp_control"] = True
    plugin._desktop_power.restore = lambda: {
        "ok": False,
        "mode": "custom",
        "detail": "restore failed",
    }
    calls = []

    async def set_tdp(enabled):
        calls.append(enabled)

    plugin.set_tdp_control_enabled = set_tdp

    state = asyncio.run(plugin.set_desktop_mode_enabled(False))

    assert state["enabled"] is True
    assert plugin._settings["desktop_mode_enabled"] is True
    assert plugin._settings["desktop_prev_tdp_control"] is True
    assert calls == []


def test_shutdown_handoff_releases_desktop_power():
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._desktop_power = Coordinator()
    plugin._restore_fans_safe = lambda: None
    plugin._restore_color_safe = lambda: None
    plugin._restore_audio_safe = lambda: None
    plugin._release_cpu_controls_sync = lambda *_args, **_kwargs: True
    plugin._release_gpu_clock_sync = lambda *_args, **_kwargs: True
    plugin._restore_power_handoff = lambda *_args, **_kwargs: True

    plugin._perform_shutdown_handoff("test")

    assert plugin._desktop_power.calls == [("restore",)]


def test_free_profile_reapply_recovers_pending_durable_handoff():
    plugin = _plugin()

    plugin._reapply_desktop_power()

    assert plugin._desktop_power.calls == [("mode", "free")]


def test_desktop_fan_state_never_fabricates_a_missing_gpu_channel():
    plugin = main.Plugin.__new__(main.Plugin)
    auto = {"preset": "auto", "points": None, "bias": 0}
    plugin._fan_curves = types.SimpleNamespace(
        effective=lambda _appid: dict(auto),
        has_game=lambda _appid: False,
        is_following_global=lambda _appid: True,
    )
    plugin._desktop_fans = types.SimpleNamespace(
        effective=lambda _appid: {"system": dict(auto), "gpu": dict(auto)})
    plugin._fan_ctrl = types.SimpleNamespace(resettable=True)
    plugin._current_appid = None
    plugin._ec_curve = None
    plugin._fan_experimental_available = False
    plugin._settings = {"fan_experimental": False}
    plugin._os_name = "Linux"
    plugin._device = detect(product_name="Fremont")
    plugin._firmware_mode = lambda: "custom"
    plugin._firmware_choices = lambda: []
    plugin._desktop_mode_on = lambda: True

    state = plugin._fan_curve_state({
        "supported": True,
        "independent": True,
        "fans": [{
            "key": "system",
            "sensor": "CPU / GPU / VRAM",
            "rpm": 800,
            "max_rpm": 1800,
            "controllable": True,
        }],
    })

    assert state["device_key"] == "steam_machine"
    assert [channel["key"] for channel in state["channels"]] == ["system"]


def test_desktop_fan_curve_reports_failed_hardware_apply():
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._desktop_mode_on = lambda: True
    plugin._resolve_scope = lambda scope, appid: scope
    plugin._fan_ctrl = types.SimpleNamespace(read_state=lambda: {
        "independent": True,
        "fans": [{"key": "system", "controllable": True}],
    })
    plugin._desktop_fans = types.SimpleNamespace(
        checkpoint=lambda: {},
        set_channel=lambda *args: None,
        restore_checkpoint=lambda _checkpoint: None,
    )
    plugin._reapply_fans = lambda: None
    plugin._reapply_fans_sync = lambda: False
    plugin._ensure_fan_loop = lambda: None

    async def offload(fn):
        return fn()

    async def state():
        return {"independent": True, "channels": [{
            "key": "system", "preset": "custom", "points": [[40, 0]],
            "controllable": True,
        }]}

    plugin._offload_call = offload
    plugin._fan_curve_state_offloop = state

    result = asyncio.run(plugin.set_desktop_fan_curve(
        "system", "custom", [[40, 0]], "global", None))

    assert result["apply_ok"] is False


def test_desktop_fan_curve_restores_previous_profile_when_apply_fails(tmp_path):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._desktop_mode_on = lambda: True
    plugin._resolve_scope = lambda scope, appid: scope
    plugin._current_appid = None
    plugin._fan_ctrl = types.SimpleNamespace(read_state=lambda: {
        "independent": True,
        "fans": [{"key": "system", "controllable": True}],
    })
    plugin._desktop_fans = DesktopFanStore(str(tmp_path / "fans.json"))
    previous = [[40, 0], [60, 80], [80, 160], [95, 255]]
    plugin._desktop_fans.set_channel("global", "system", "balanced", previous)
    plugin._reapply_fans_sync = lambda: False
    plugin._ensure_fan_loop = lambda: None

    async def offload(fn):
        return fn()

    async def state():
        profile = plugin._desktop_fans.effective(None)["system"]
        return {"independent": True, "channels": [{
            "key": "system", "preset": profile["preset"], "points": profile["points"],
            "controllable": True,
        }]}

    plugin._offload_call = offload
    plugin._fan_curve_state_offloop = state

    result = asyncio.run(plugin.set_desktop_fan_curve(
        "system", "custom", [[40, 20], [95, 255]], "global", None))

    assert result["apply_ok"] is False
    assert result["channels"][0]["preset"] == "balanced"
    assert plugin._desktop_fans.effective(None)["system"]["points"] == previous


def test_desktop_fan_reapply_skips_missing_channels():
    calls = []
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._module_enabled = lambda _module: True
    plugin._desktop_mode_on = lambda: True
    plugin._current_appid = None
    plugin._desktop_fans = types.SimpleNamespace(effective=lambda _appid: {
        "system": {"preset": "custom", "points": [[40, 0], [95, 255]]},
        "gpu": {"preset": "custom", "points": [[40, 0], [95, 255]]},
    })
    plugin._fan_ctrl = types.SimpleNamespace(
        read_state=lambda: {
            "independent": True,
            "fans": [{"key": "system", "controllable": True}],
        },
        set_curve=lambda channel, _points: calls.append(channel) or {"ok": channel == "system"},
        set_auto=lambda channel: calls.append(channel) or {"ok": channel == "system"},
    )

    assert plugin._reapply_fans_sync() is True
    assert calls == ["system"]


def test_desktop_fan_mutations_are_serialized_while_hardware_apply_is_pending():
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []
        offloads = 0
        plugin = main.Plugin.__new__(main.Plugin)
        plugin._init = lambda: None
        plugin._desktop_mode_on = lambda: True
        plugin._resolve_scope = lambda scope, appid: scope
        plugin._fan_ctrl = types.SimpleNamespace(read_state=lambda: {
            "independent": True,
            "fans": [{"key": "system", "controllable": True}],
        })
        plugin._desktop_fans = types.SimpleNamespace(
            checkpoint=lambda: {},
            set_channel=lambda *args: calls.append(args),
            restore_checkpoint=lambda _checkpoint: None,
        )
        plugin._reapply_fans_sync = lambda: True
        plugin._ensure_fan_loop = lambda: None

        async def offload(fn):
            nonlocal offloads
            offloads += 1
            if offloads == 1:
                entered.set()
                await release.wait()
            return fn()

        async def state():
            return {"independent": True, "channels": []}

        plugin._offload_call = offload
        plugin._fan_curve_state_offloop = state

        first = asyncio.create_task(plugin.set_desktop_fan_curve(
            "system", "custom", [[40, 0]], "global", None))
        await entered.wait()
        second = asyncio.create_task(plugin.set_desktop_fan_curve(
            "system", "custom", [[50, 20]], "global", None))
        await asyncio.sleep(0)

        assert len(calls) == 1
        release.set()
        await asyncio.gather(first, second)
        assert len(calls) == 2

    asyncio.run(scenario())
