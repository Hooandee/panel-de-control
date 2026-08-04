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
        self.virtual_mode = {}

    def effective_profile(self, appid):
        value = 20 if appid == "10" else 80
        return {
            "virtual_controller": dict(self.virtual_mode),
            "buttons": {},
            "vibration": {"value": value},
        }

    def get_config(self, appid):
        return {
            "manager": self.manager,
            "manager_version": "test",
            "supported": True,
            "kind": "remap",
            "virtual_controller": {
                "supported": True,
                "mode": self.virtual_mode.get("mode", "auto"),
                "actual_mode": "uinput",
                "options": ["auto", "uinput", "dualsense"],
                "scope": ["global", "game"],
            },
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

    def test_vibration(self, pattern, channel, strength):
        self.calls.append(("test", pattern, channel, strength))
        return {
            "sent": True,
            "stopped": True,
            "restored": True,
            "reason": None,
        }

    def set_virtual_mode(self, mode, scope, appid):
        self.virtual_mode = {"mode": mode}
        return self.get_config(appid)


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
    plugin._controller_endpoint_last = ("old-controller",)
    plugin._display_endpoint_last = ("old-display",)
    plugin._controller_endpoint_pending = ("pending-controller",)
    plugin._display_endpoint_pending = ("pending-display",)
    plugin._controller_endpoint_attempts = 4
    plugin._display_endpoint_attempts = 4

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
    assert plugin._controller_endpoint_last is None
    assert plugin._display_endpoint_last is None
    assert plugin._controller_endpoint_pending is None
    assert plugin._display_endpoint_pending is None
    assert plugin._controller_endpoint_attempts == 0
    assert plugin._display_endpoint_attempts == 0


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


def test_vibration_rpc_cancels_previous_transient_and_returns_result(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    backend = LifecycleBackend()
    plugin._controller_backend = backend
    plugin._controller_coordinator = ControllerCoordinator(backend)
    plugin._init = lambda: None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    result = asyncio.run(plugin.test_controller_vibration(
        "pulse", "left", 50
    ))

    assert backend.calls == [
        ("cancel", "superseded"),
        ("test", "pulse", "left", 50),
    ]
    assert result == {
        "sent": True,
        "stopped": True,
        "restored": True,
        "reason": None,
    }


def test_virtual_mode_rpc_persists_then_reconciles_dependents(
    tmp_path, monkeypatch
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    backend = LifecycleBackend()
    plugin._controller_backend = backend
    plugin._controller_coordinator = ControllerCoordinator(backend)
    plugin._controller_shutdown = False
    plugin._current_appid = "42"
    plugin._module_enabled = lambda module: module == "mandos"
    plugin._init = lambda: None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    config = asyncio.run(plugin.set_controller_virtual_mode(
        "dualsense", "game", "42"
    ))

    assert config["virtual_controller"]["mode"] == "dualsense"
    assert backend.calls == [
        ("virtual_controller", "42"),
        ("wait_ready", "42"),
        ("buttons", "42"),
        ("vibration", "42"),
    ]


def test_endpoint_poll_reapplies_once_when_lenovo_hd_reconnects(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)

    class Backend:
        manager = "inputplumber"

        def __init__(self):
            self.connected = False

        def get_config(self, appid):
            return {
                "vibration": {
                    "mode": "lenovo_hd",
                    "connected": self.connected,
                },
            }

    backend = Backend()
    plugin._controller_backend = backend
    plugin._device = types.SimpleNamespace(key="legion_go_2")
    plugin._current_appid = "42"
    plugin._controller_endpoint_last = (
        "inputplumber", "lenovo_hd", False, (), (),
    )

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    reapplies = []

    async def reconcile(force=False):
        reapplies.append(force)
        return True

    plugin._reconcile_controller_now = reconcile
    backend.connected = True

    asyncio.run(plugin._poll_controller_endpoint_once())
    asyncio.run(plugin._poll_controller_endpoint_once())

    assert reapplies == [True]


def test_endpoint_poll_reapplies_xbox_profile_after_inputplumber_restart(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)

    plugin._controller_backend = types.SimpleNamespace(manager="inputplumber")
    plugin._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    plugin._current_appid = "42"
    plugin._controller_endpoint_last = None
    state = {"ready": False}
    desired = {
        "hd_game_enabled": True,
        "trigger_left": 60,
        "trigger_right": 40,
        "trigger_left_source": "mix",
        "trigger_right_source": "weak",
    }
    plugin._controller_dbus = types.SimpleNamespace(
        xbox_hd_haptics=lambda: (
            {
                "enabled": False,
                "trigger_left": 100,
                "trigger_right": 100,
                "trigger_left_source": "strong",
                "trigger_right_source": "weak",
            }
            if state["ready"] else None
        )
    )
    plugin._controller_store = types.SimpleNamespace(
        effective_vibration=lambda _appid: desired
    )

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    reapplies = []

    async def reconcile(force=False):
        reapplies.append(force)
        return True

    plugin._reconcile_controller_now = reconcile

    asyncio.run(plugin._poll_controller_endpoint_once())
    state["ready"] = True
    asyncio.run(plugin._poll_controller_endpoint_once())
    asyncio.run(plugin._poll_controller_endpoint_once())

    assert reapplies == [True]


def test_endpoint_poll_skips_non_go2_controller_backends(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)

    class Backend:
        manager = "hhd"

        def get_config(self, appid):
            raise AssertionError("non-Go2 backend must not be polled")

    plugin._controller_backend = Backend()
    plugin._device = types.SimpleNamespace(key="rog_ally")
    plugin._current_appid = "42"
    plugin._controller_endpoint_last = None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload

    asyncio.run(plugin._poll_controller_endpoint_once())

    assert plugin._controller_endpoint_last is None


def test_endpoint_poll_retries_failed_lenovo_hd_reapply(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._controller_backend = types.SimpleNamespace(
        manager="inputplumber",
        get_config=lambda _appid: {
            "vibration": {"mode": "lenovo_hd", "connected": True}
        },
    )
    plugin._device = types.SimpleNamespace(key="legion_go_2")
    plugin._current_appid = "42"
    previous = ("inputplumber", "lenovo_hd", False, (), ())
    plugin._controller_endpoint_last = previous

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    outcomes = iter((False, True))
    reapplies = []

    async def reconcile(force=False):
        reapplies.append(force)
        return next(outcomes)

    plugin._reconcile_controller_now = reconcile

    asyncio.run(plugin._poll_controller_endpoint_once())
    assert plugin._controller_endpoint_last == previous
    asyncio.run(plugin._poll_controller_endpoint_once())
    asyncio.run(plugin._poll_controller_endpoint_once())

    assert reapplies == [True, True]
    assert plugin._controller_endpoint_last[:3] == (
        "inputplumber", "lenovo_hd", True,
    )


def test_endpoint_poll_reapplies_when_lenovo_readback_resets_while_connected(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    values = {"desired": "high", "actual": "high"}

    def config(_appid):
        return {
            "vibration": {
                "mode": "lenovo_hd",
                "connected": True,
                "intensity": values["desired"],
                "actual_intensity": values["actual"],
            }
        }

    plugin._controller_backend = types.SimpleNamespace(
        manager="inputplumber", get_config=config,
    )
    plugin._device = types.SimpleNamespace(key="legion_go_2")
    plugin._current_appid = "42"
    plugin._controller_endpoint_last = None

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    reapplies = []

    async def reconcile(force=False):
        reapplies.append(force)
        values["actual"] = values["desired"]
        return True

    plugin._reconcile_controller_now = reconcile

    asyncio.run(plugin._poll_controller_endpoint_once())
    values["actual"] = "medium"
    asyncio.run(plugin._poll_controller_endpoint_once())
    asyncio.run(plugin._poll_controller_endpoint_once())

    assert reapplies == [True, True]


def test_endpoint_poll_initial_apply_has_bounded_retry_budget(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._controller_backend = types.SimpleNamespace(
        manager="inputplumber",
        get_config=lambda _appid: {
            "vibration": {"mode": "lenovo_hd", "connected": True}
        },
    )
    plugin._device = types.SimpleNamespace(key="legion_go_2")
    plugin._current_appid = None
    plugin._controller_endpoint_last = None
    plugin._hardware_retry_limit = 2

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    calls = []

    async def reconcile(force=False):
        calls.append(force)
        return False

    plugin._reconcile_controller_now = reconcile

    for _ in range(4):
        asyncio.run(plugin._poll_controller_endpoint_once())

    assert calls == [True, True]
    assert plugin._controller_endpoint_last is None


def test_endpoint_poll_counts_apply_exceptions_against_retry_budget(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._controller_backend = types.SimpleNamespace(
        manager="inputplumber",
        get_config=lambda _appid: {
            "vibration": {"mode": "lenovo_hd", "connected": True}
        },
    )
    plugin._device = types.SimpleNamespace(key="legion_go_2")
    plugin._current_appid = None
    plugin._controller_endpoint_last = None
    plugin._hardware_retry_limit = 2

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    calls = []

    async def reconcile(force=False):
        calls.append(force)
        raise OSError("transient")

    plugin._reconcile_controller_now = reconcile

    for _ in range(4):
        asyncio.run(plugin._poll_controller_endpoint_once())

    assert calls == [True, True]


def test_display_poll_reapplies_hdr_then_color_on_connector_change(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._color_backend = types.SimpleNamespace(
        display_fingerprint=lambda: ("eDP-1", True)
    )
    plugin._display_endpoint_last = ("DP-1", False)
    events = []

    async def offload(fn):
        return fn()

    plugin._offload_call = offload

    async def reapply():
        events.extend(("hdr", "color"))
        return True

    plugin._reapply_display_endpoint_now = reapply

    asyncio.run(plugin._poll_display_endpoint_once())
    asyncio.run(plugin._poll_display_endpoint_once())

    assert events == ["hdr", "color"]


def test_display_poll_retries_failed_reapply(tmp_path, monkeypatch):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._color_backend = types.SimpleNamespace(
        display_fingerprint=lambda: ("eDP-1", True)
    )
    previous = ("DP-1", False)
    plugin._display_endpoint_last = previous

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    outcomes = iter((False, True))
    calls = []

    async def reapply():
        calls.append(True)
        return next(outcomes)

    plugin._reapply_display_endpoint_now = reapply

    asyncio.run(plugin._poll_display_endpoint_once())
    assert plugin._display_endpoint_last == previous
    asyncio.run(plugin._poll_display_endpoint_once())
    asyncio.run(plugin._poll_display_endpoint_once())

    assert calls == [True, True]
    assert plugin._display_endpoint_last == ("eDP-1", True)


def test_display_poll_initial_apply_has_bounded_retry_budget(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._color_backend = types.SimpleNamespace(
        display_fingerprint=lambda: ("eDP-1", True)
    )
    plugin._display_endpoint_last = None
    plugin._hardware_retry_limit = 2

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    calls = []

    async def reapply():
        calls.append(True)
        return False

    plugin._reapply_display_endpoint_now = reapply

    for _ in range(4):
        asyncio.run(plugin._poll_display_endpoint_once())

    assert calls == [True, True]
    assert plugin._display_endpoint_last is None


def test_display_poll_counts_apply_exceptions_against_retry_budget(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._color_backend = types.SimpleNamespace(
        display_fingerprint=lambda: ("eDP-1", True)
    )
    plugin._display_endpoint_last = None
    plugin._hardware_retry_limit = 2

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    calls = []

    async def reapply():
        calls.append(True)
        raise OSError("transient")

    plugin._reapply_display_endpoint_now = reapply

    for _ in range(4):
        asyncio.run(plugin._poll_display_endpoint_once())

    assert calls == [True, True]


def test_display_restore_failures_are_reported(tmp_path, monkeypatch):
    main = _main(monkeypatch, tmp_path)
    warnings = []
    main.decky.logger.warning = lambda *args: warnings.append(args)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._color_backend = types.SimpleNamespace(
        release=lambda: False,
        diagnostics=lambda: {"last_apply": {"ok": False, "rc": 1}},
    )
    plugin._hdr_managed = True
    plugin._hdr_backend = types.SimpleNamespace(
        set_enabled=lambda _enabled: False
    )

    assert plugin._restore_color_safe() is False
    assert plugin._restore_hdr_safe() is False

    assert [entry[0] for entry in warnings] == [
        "Color ownership release failed: %s",
        "HDR ownership release failed: %s",
    ]
    assert warnings[1][1] == {"enabled": False, "ok": False, "rc": None}


def test_hdr_ownership_is_discarded_without_write_on_new_gamescope_session(
    tmp_path, monkeypatch,
):
    main = _main(monkeypatch, tmp_path)
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._device = types.SimpleNamespace(hdr=True)
    plugin._color = types.SimpleNamespace(hdr=lambda _appid: False)
    plugin._current_appid = None
    plugin._color_backend = types.SimpleNamespace(
        supported=True, session_identity=(2, 200),
    )
    calls = []
    plugin._hdr_backend = types.SimpleNamespace(
        set_enabled=lambda enabled: calls.append(enabled) or True
    )
    plugin._hdr_managed = True
    plugin._hdr_managed_session = (1, 100)

    assert plugin._reapply_hdr_sync() is True

    assert calls == []
    assert plugin._hdr_managed is False
    assert plugin._hdr_managed_session is None
