import importlib
import asyncio
import sys
import types

from controllers.coordinator import ControllerCoordinator
from controllers.operations import OperationResult


def _main(monkeypatch, tmp_path):
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "decky", decky)
    return importlib.reload(importlib.import_module("main"))


class LifecycleBackend:
    manager = "inputplumber"

    def __init__(self):
        self.calls = []

    def effective_profile(self, appid):
        value = 20 if appid == "10" else 80
        return {
            "virtual_controller": {},
            "buttons": {},
            "vibration": {"value": value},
        }

    def get_config(self, appid):
        return {
            "manager": self.manager,
            "manager_version": "test",
            "supported": True,
            "kind": "remap",
        }

    def owns_loaded_profile(self):
        return True

    def apply_component(self, component, desired, appid, generation):
        self.calls.append((component, appid))
        return OperationResult(
            component, "applied", None, self.manager,
            generation, appid, desired, desired,
        )

    def wait_ready(self, appid, generation):
        self.calls.append(("wait_ready", appid))
        return True

    def cancel_transients(self, reason):
        self.calls.append(("cancel", reason))

    def clear_translated_state(self):
        return True

    def restore_external(self):
        return True


def test_game_switch_generation_is_captured_before_worker_runs(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    backend = LifecycleBackend()
    plugin._controller_backend = backend
    plugin._controller_coordinator = ControllerCoordinator(backend)
    plugin._controller_shutdown = False
    plugin._module_enabled = lambda module: True
    queued = []
    plugin._offload = lambda fn, done=None: queued.append(fn)

    plugin._current_appid = "10"
    plugin._reapply_controller(force=True)
    plugin._current_appid = "20"
    plugin._reapply_controller(force=True)

    queued[0]()
    queued[1]()

    snapshot = plugin._controller_coordinator.snapshot()
    assert snapshot["appid"] == "20"
    assert snapshot["components"]["vibration"]["desired"] == {"value": 80}
    assert ("vibration", "10") not in backend.calls


def test_resume_cancels_transients_and_refreshes_before_reapply(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    events = []
    plugin._controller_coordinator = types.SimpleNamespace(
        cancel_transients=lambda reason: events.append(("cancel", reason))
    )
    plugin._refresh_controller_backend = lambda: events.append(("refresh", None))
    plugin._reapply_all = lambda *args, **kwargs: events.append(("reapply", kwargs))

    def offload(fn, done=None):
        fn()
        if done is not None:
            done()

    plugin._offload = offload
    plugin._reapply_after_resume(on_ac=True)

    assert events == [
        ("cancel", "resume"),
        ("refresh", None),
        ("reapply", {"force_controller": True}),
    ]


def test_shutdown_invalidates_already_prepared_reconcile(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    backend = LifecycleBackend()
    coordinator = ControllerCoordinator(backend)
    plugin._controller_coordinator = coordinator
    plugin._controller_shutdown = False
    request = coordinator.prepare("10", backend.effective_profile("10"))

    plugin._begin_controller_shutdown()
    coordinator.execute(request)

    assert plugin._controller_shutdown is True
    assert backend.calls == []


def test_controller_config_exposes_component_operation_state(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    backend = LifecycleBackend()
    coordinator = ControllerCoordinator(backend)
    coordinator.reconcile("20", backend.effective_profile("20"))
    plugin._controller_backend = backend
    plugin._controller_coordinator = coordinator
    plugin._current_appid = "20"
    plugin._init = lambda: None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    config = asyncio.run(plugin.get_controller_config())

    assert config["operation_state"]["appid"] == "20"
    assert config["operation_state"]["components"]["vibration"] == {
        "status": "applied",
        "owner": "inputplumber",
        "desired": {"value": 80},
        "actual": {"value": 80},
    }
