import asyncio
import sys
import types


if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER_HOME = "/tmp"
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["decky"] = decky

import main


class ActionBackend:
    def __init__(self):
        self.calls = []

    def run_action(self, action):
        self.calls.append(action)
        return {
            "action": action,
            "outcome": "confirmed",
            "accepted": True,
            "modules": {"left": "disconnected", "right": "connected"},
        }

    def get_config(self, appid=None):
        return {
            "kind": "settings",
            "manager": "hhd",
            "magic_modules": {
                "supported": True,
                "source": "hhd",
                "left": "disconnected",
                "right": "connected",
                "busy": False,
            },
        }


def test_controller_action_runs_offloop_and_returns_refreshed_config():
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._current_appid = None
    plugin._controller_backend = ActionBackend()
    plugin._controller_action_inflight = False
    offloaded = []

    async def offload_action(call):
        offloaded.append("action")
        return call()

    async def offload(call):
        offloaded.append("read")
        return call()

    plugin._offload_controller_action_call = offload_action
    plugin._offload_call = offload

    result = asyncio.run(plugin.run_controller_action("eject_left"))

    assert plugin._controller_backend.calls == ["eject_left"]
    assert offloaded == ["action", "read"]
    assert result["outcome"] == "confirmed"
    assert result["config"]["magic_modules"]["left"] == "disconnected"


def test_controller_action_rejects_a_second_rpc_before_it_reaches_the_executor():
    async def scenario():
        plugin = main.Plugin.__new__(main.Plugin)
        plugin._init = lambda: None
        plugin._current_appid = None
        plugin._controller_backend = ActionBackend()
        plugin._controller_action_inflight = False
        started = asyncio.Event()
        release = asyncio.Event()

        async def offload_action(call):
            started.set()
            await release.wait()
            return call()

        async def offload(call):
            return call()

        plugin._offload_controller_action_call = offload_action
        plugin._offload_call = offload

        first = asyncio.create_task(plugin.run_controller_action("eject_left"))
        await started.wait()
        second = await plugin.run_controller_action("eject_right")
        release.set()
        completed = await first
        return plugin, second, completed

    plugin, second, completed = asyncio.run(scenario())

    assert plugin._controller_backend.calls == ["eject_left"]
    assert second["outcome"] == "busy"
    assert second["reason"] == "action_in_progress"
    assert completed["outcome"] == "confirmed"
