import asyncio
import os
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
from device_profiles import DeviceProfile
from fans.ps5_target import FIRMWARE_DEFAULT_C, Ps5FanTarget

PS5 = DeviceProfile("playstation_5", "PlayStation 5", "AMD Oberon", "amd", 4, 10, 30, 30)


def _node(root, value="80"):
    path = os.path.join(root, "sys/bus/platform/devices/ps5-fan/target_temp")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(value)
    return path


def _read(path):
    with open(path) as handle:
        return handle.read().strip()


class NullCtrl:
    name = "null"
    supported = False

    def restore_auto(self):
        return {"ok": False}


def _plugin(root, enabled=True):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._device = PS5
    plugin._settings = {"ps5_fan_target_c": None, "fremont_fan_handoff_pending": False}
    plugin._ps5_fan = Ps5FanTarget(root=root)
    plugin._fan_ctrl = NullCtrl()
    plugin._save = lambda: None
    plugin._module_enabled = lambda name: enabled

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    return plugin


def test_user_target_is_written_saved_and_reported(tmp_path):
    path = _node(str(tmp_path))
    plugin = _plugin(str(tmp_path))
    state = asyncio.run(plugin.set_fan_target_temp(65))
    assert _read(path) == "65"
    assert plugin._settings["ps5_fan_target_c"] == 65
    assert state["ok"] is True and state["celsius"] == 65 and state["target"] == 65


def test_failed_write_keeps_the_previous_target(tmp_path, monkeypatch):
    _node(str(tmp_path))
    plugin = _plugin(str(tmp_path))
    plugin._settings["ps5_fan_target_c"] = 70
    monkeypatch.setattr("ps5.firmware_io.FirmwareIo.write", lambda self, path, value: "errno_5")
    state = asyncio.run(plugin.set_fan_target_temp(55))
    assert state["ok"] is False
    assert plugin._settings["ps5_fan_target_c"] == 70


def test_reset_returns_the_firmware_default(tmp_path):
    path = _node(str(tmp_path), "60")
    plugin = _plugin(str(tmp_path))
    plugin._settings["ps5_fan_target_c"] = 60
    state = asyncio.run(plugin.set_fan_target_temp(None))
    assert _read(path) == str(FIRMWARE_DEFAULT_C)
    assert state["target"] is None


def test_release_on_unload_only_when_panel_set_a_target(tmp_path):
    path = _node(str(tmp_path), "60")
    plugin = _plugin(str(tmp_path))
    plugin._restore_fans_safe()
    assert _read(path) == "60"
    plugin._settings["ps5_fan_target_c"] = 60
    plugin._restore_fans_safe()
    assert _read(path) == str(FIRMWARE_DEFAULT_C)


def test_reapply_restores_the_saved_target(tmp_path):
    path = _node(str(tmp_path), "80")
    plugin = _plugin(str(tmp_path))
    plugin._settings["ps5_fan_target_c"] = 70
    plugin._reapply_ps5_fan_sync()
    assert _read(path) == "70"


def test_disabled_fan_module_never_writes(tmp_path):
    path = _node(str(tmp_path), "80")
    plugin = _plugin(str(tmp_path), enabled=False)
    plugin._settings["ps5_fan_target_c"] = 70
    plugin._reapply_ps5_fan_sync()
    assert _read(path) == "80"
    assert asyncio.run(plugin.set_fan_target_temp(60))["ok"] is False


def test_other_devices_report_unsupported(tmp_path):
    plugin = _plugin(str(tmp_path))
    plugin._ps5_fan = None
    assert asyncio.run(plugin.set_fan_target_temp(60)) == {"supported": False}


def test_out_of_range_target_is_saved_as_written(tmp_path):
    path = _node(str(tmp_path))
    plugin = _plugin(str(tmp_path))
    state = asyncio.run(plugin.set_fan_target_temp(95))
    assert _read(path) == "90"
    assert plugin._settings["ps5_fan_target_c"] == 90 and state["target"] == 90
    assert asyncio.run(plugin.set_fan_target_temp(True))["detail"] == "invalid_value"
    assert plugin._settings["ps5_fan_target_c"] == 90


def test_failed_reset_keeps_the_target_for_unload(tmp_path, monkeypatch):
    _node(str(tmp_path), "60")
    plugin = _plugin(str(tmp_path))
    plugin._settings["ps5_fan_target_c"] = 60
    monkeypatch.setattr("ps5.firmware_io.FirmwareIo.write", lambda self, path, value: "errno_5")
    state = asyncio.run(plugin.set_fan_target_temp(None))
    assert state["ok"] is False
    assert plugin._settings["ps5_fan_target_c"] == 60


class _Boost:
    def __init__(self, on):
        self.supported = True
        self._on = on

    def enabled(self):
        return self._on


def test_gpu_limit_is_flagged_only_on_the_ps5_with_boost_on(tmp_path):
    plugin = _plugin(str(tmp_path))
    plugin._boost = _Boost(True)
    assert plugin._gpu_limit_overridden_by_boost() is True
    plugin._boost = _Boost(False)
    assert plugin._gpu_limit_overridden_by_boost() is False
    plugin._device = DeviceProfile("generic", "Generic", "AMD", "amd", 4, 10, 30, 30)
    plugin._boost = _Boost(True)
    assert plugin._gpu_limit_overridden_by_boost() is False


def test_failed_startup_apply_is_retried_until_confirmed(tmp_path, monkeypatch):
    path = _node(str(tmp_path), "80")
    plugin = _plugin(str(tmp_path))
    plugin._settings["ps5_fan_target_c"] = 70
    monkeypatch.setattr(main, "_AUTO_APPLY_RETRY_DELAYS_S", (0.01, 0.01, 0.01))
    failures = iter(["errno_19", None])
    from ps5.firmware_io import FirmwareIo
    real_write = FirmwareIo.write

    def flaky(self, node, value):
        error = next(failures, None)
        return error if error else real_write(self, node, value)

    monkeypatch.setattr("ps5.firmware_io.FirmwareIo.write", flaky)

    def offload(fn, done=None):
        fn()
        if done:
            done()

    plugin._offload = offload

    async def run():
        plugin._reapply_ps5_fan_sync()
        plugin._schedule_ps5_fan_retry()
        await asyncio.sleep(0.1)

    asyncio.run(run())
    assert _read(path) == "70"
    assert plugin._ps5_fan_pending is False


def test_other_ps5_plugin_is_detected_by_name(tmp_path):
    plugin = _plugin(str(tmp_path))
    plugins = tmp_path / "plugins"
    (plugins / "ps5-hardware-control").mkdir(parents=True)
    (plugins / "ps5-hardware-control" / "plugin.json").write_text('{"name": "PS5 Hardware Control"}')
    plugin._decky_plugins_root = lambda: plugins
    assert plugin._ps5_rival_plugin() == "PS5 Hardware Control"


def test_each_fresh_reapply_gets_its_own_retries(tmp_path, monkeypatch):
    plugin = _plugin(str(tmp_path))
    plugin._ensure_fan_loop = lambda: None
    plugin._ps5_fan_pending = True
    plugin._ps5_fan_retries = 3
    scheduled = []

    class Loop:
        def call_later(self, delay, fn):
            scheduled.append(delay)

    monkeypatch.setattr(main.asyncio, "get_running_loop", lambda: Loop())
    plugin._after_fan_reapply()
    assert scheduled == [main._AUTO_APPLY_RETRY_DELAYS_S[0]]
