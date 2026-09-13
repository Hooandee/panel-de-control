import asyncio
import json
import sys
import threading
import types

import pytest

if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["decky"] = decky

import main


@pytest.fixture
def plugin(monkeypatch):
    instance = main.Plugin.__new__(main.Plugin)
    instance._init = lambda: None
    yield instance
    close = getattr(instance, "_close_steam_cleaner_sync", None)
    if close:
        close()


class BlockingService:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False
        self.thread_id = None

    def inventory(self):
        self.thread_id = threading.get_ident()
        self.started.set()
        if not self.release.wait(3):
            raise RuntimeError("test worker not released")
        return {"status": "ready"}

    def get_state(self):
        return {"status": "scanning" if self.started.is_set() else "idle"}

    def cancel(self):
        self.release.set()
        return {"status": "cancelled"}

    def close(self):
        self.closed = True
        self.release.set()


def install_service(plugin, service):
    plugin._steam_cleaner = service
    return service


async def await_started(service):
    for _ in range(100):
        if service.started.is_set():
            return
        await asyncio.sleep(0.005)
    pytest.fail("cleaner worker did not start")


def test_first_state_before_main_initializes_offloop_without_scanning(plugin, monkeypatch):
    constructed = []
    constructor_threads = []

    def create(home, *, logger, state_dir):
        constructed.append((home, state_dir))
        constructor_threads.append(threading.get_ident())
        return BlockingService()

    monkeypatch.setattr(main, "SteamCleanerService", create, raising=False)
    monkeypatch.setattr(main.decky, "DECKY_USER_HOME", "/home/player", raising=False)
    monkeypatch.setattr(main.decky, "DECKY_PLUGIN_SETTINGS_DIR", "/tmp/plugin-settings")
    assert asyncio.run(plugin.get_steam_cleaner_state()) == {"status": "idle"}
    assert asyncio.run(plugin.get_steam_cleaner_state()) == {"status": "idle"}
    assert constructed == [("/home/player", "/tmp/plugin-settings/steam_cleaner")]
    assert constructor_threads[0] != threading.get_ident()
    assert not plugin._steam_cleaner.started.is_set()


def test_scan_keeps_state_rpc_responsive_and_rejects_duplicate_work(plugin):
    service = install_service(plugin, BlockingService())

    async def scenario():
        operation = asyncio.create_task(plugin.scan_steam_cleaner())
        try:
            await await_started(service)
            assert service.thread_id != threading.get_ident()
            assert await plugin.get_steam_cleaner_state() == {"status": "scanning"}
            for call in (
                plugin.scan_steam_cleaner(),
                plugin.prepare_steam_cleaner("scan", ["entry"]),
                plugin.execute_steam_cleaner("plan", False),
            ):
                with pytest.raises(RuntimeError, match="^busy$"):
                    await asyncio.wait_for(call, 0.2)
            assert await plugin.cancel_steam_cleaner() == {"status": "cancelled"}
        finally:
            service.release.set()
            assert await operation == {"status": "ready"}

    asyncio.run(scenario())


def test_cancelled_rpc_stays_busy_until_worker_finishes(plugin):
    service = install_service(plugin, BlockingService())

    async def scenario():
        operation = asyncio.create_task(plugin.scan_steam_cleaner())
        try:
            await await_started(service)
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
            with pytest.raises(RuntimeError, match="^busy$"):
                await asyncio.wait_for(plugin.scan_steam_cleaner(), 0.2)
        finally:
            service.release.set()

    asyncio.run(scenario())


def test_rpc_masks_unexpected_exception_text(plugin):
    service = install_service(plugin, BlockingService())

    def fail():
        raise OSError("cannot access /home/player/private-save")

    service.inventory = fail
    with pytest.raises(RuntimeError, match="^internal_error$"):
        asyncio.run(plugin.scan_steam_cleaner())


def test_rpc_preserves_safe_service_error_code(plugin):
    service = install_service(plugin, BlockingService())

    def refuse(*args):
        raise main.SteamCleanerError("prefix_confirmation_required")

    service.execute = refuse
    with pytest.raises(RuntimeError, match="^prefix_confirmation_required$"):
        asyncio.run(plugin.execute_steam_cleaner("plan-1", False))


def test_shutdown_drains_constructor_that_has_not_published_service(plugin, monkeypatch):
    service = BlockingService()
    constructing = threading.Event()
    release_constructor = threading.Event()

    def create(home, *, logger, state_dir):
        constructing.set()
        if not release_constructor.wait(3):
            raise RuntimeError("test constructor not released")
        return service

    monkeypatch.setattr(main, "SteamCleanerService", create)
    monkeypatch.setattr(main.decky, "DECKY_USER_HOME", "/home/player", raising=False)

    async def scenario():
        state = asyncio.create_task(plugin.get_steam_cleaner_state())
        try:
            for _ in range(100):
                if constructing.is_set():
                    break
                await asyncio.sleep(0.005)
            assert constructing.is_set()
            release_constructor.set()
            plugin._close_steam_cleaner_sync()
            assert service.closed
            assert plugin._steam_cleaner_executor is None
            with pytest.raises(RuntimeError, match="^closed$"):
                await state
        finally:
            release_constructor.set()

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ["_unload", "_uninstall"])
def test_shutdown_closes_active_cleaner_before_hardware_handoff(plugin, monkeypatch, method):
    service = install_service(plugin, BlockingService())
    for name in (
        "_cancel_charge_limit_reconcile", "_stop_charge_limit_full_once_monitor",
        "_next_cpu_generation", "_next_gpu_generation", "_begin_theme_shutdown",
        "_begin_tdp_shutdown", "_cancel_color_revert", "_stop_night_loop",
        "_cancel_queued_offloads", "_shutdown_apply_executor",
        "_shutdown_controller_action_executor", "_finish_theme_shutdown_sync",
    ):
        setattr(plugin, name, lambda *args, **kwargs: None)
    plugin._hud_shutdown = True
    preparation = []
    plugin._begin_tdp_shutdown = lambda: preparation.append("tdp-stopped")
    plugin._cancel_queued_offloads = lambda: preparation.append("queues-cancelled")
    close_service = service.close

    def close_after_producers():
        assert plugin._cpu_shutdown and plugin._gpu_shutdown
        assert preparation == ["tdp-stopped", "queues-cancelled"]
        close_service()

    service.close = close_after_producers
    plugin._drain_offloaded_sync = lambda timeout: True
    handoffs = []
    plugin._perform_shutdown_handoff = lambda stage: handoffs.append(service.closed)
    monkeypatch.setattr(main.fan_expose, "remove_conf", lambda: None)

    async def scenario():
        operation = asyncio.create_task(plugin.scan_steam_cleaner())
        await await_started(service)
        shutdown = getattr(plugin, method)()
        with pytest.raises(StopIteration):
            shutdown.send(None)
        assert handoffs == [True]
        assert plugin._steam_cleaner_executor is None
        assert service.closed
        with pytest.raises(RuntimeError, match="^closed$"):
            await plugin.scan_steam_cleaner()
        await operation

    asyncio.run(scenario())


def stub_other_report_sources(plugin, monkeypatch):
    async def empty(*args, **kwargs):
        return {}

    for name in (
        "get_device", "get_tdp_state", "get_tdp_conflict", "get_fan_curve_state",
        "get_fan_state", "get_battery_state", "get_cpu_state", "get_color_state",
        "get_gpu_clock", "get_power_draw", "get_eco_state", "get_audio_state",
        "_hud_call", "_offload_call",
    ):
        setattr(plugin, name, empty)
    for name in (
        "_tdp_diagnostics", "_cpu_gpu_diagnostics", "_safe_controller_config",
        "_launch_report_state", "_report_environment", "_report_stores",
    ):
        setattr(plugin, name, lambda *args: {})
    plugin._lifecycle = types.SimpleNamespace(diagnostics=lambda: {})
    plugin._controller_backend = types.SimpleNamespace(diagnostics=lambda: {}, manager=None)
    plugin._audio = types.SimpleNamespace(diagnostics=lambda: {})
    plugin._run_capture = lambda *args: None
    for name in ("tail_logs", "sysfs_snapshot", "kernel_logs"):
        monkeypatch.setattr(main.report_collector, name, lambda *args, **kwargs: {})


def test_report_includes_bounded_redacted_cleaner_snapshot_without_scan(plugin, monkeypatch):
    stub_other_report_sources(plugin, monkeypatch)
    service = install_service(plugin, BlockingService())
    service.diagnostics = lambda: {
        "schema_version": 1,
        "phase": "ready",
        "events": [{"event": "skipped", "detail": "/home/player/cache"}] * 200,
    }
    bundle = asyncio.run(plugin._build_report_bundle([], "", "/home/player", None))
    snapshot = bundle["state"]["steam_cleaner"]
    assert not service.started.is_set()
    assert len(snapshot["events"]) <= 120
    assert len(json.dumps(snapshot).encode()) <= 48_000
    assert "/home/player" not in json.dumps(snapshot)
    assert snapshot["phase"] == "ready"


def test_first_report_recovers_journal_without_opening_cleaner(plugin, monkeypatch):
    stub_other_report_sources(plugin, monkeypatch)
    service = BlockingService()
    service.diagnostics = lambda: {
        "schema_version": 1, "phase": "interrupted", "interrupted": True,
        "events": [{"event": "interrupted", "operation_id": "cleanup-1"}],
    }
    constructor_threads = []

    def create(home, *, logger, state_dir):
        constructor_threads.append(threading.get_ident())
        return service

    monkeypatch.setattr(main, "SteamCleanerService", create)
    monkeypatch.setattr(main.decky, "DECKY_USER_HOME", "/home/player", raising=False)
    bundle = asyncio.run(plugin._build_report_bundle([], "", "/home/player", None))
    assert bundle["state"]["steam_cleaner"]["interrupted"] is True
    assert constructor_threads[0] != threading.get_ident()
    assert not service.started.is_set()


def test_cleaner_diagnostic_failure_does_not_break_report_snapshot(plugin):
    service = install_service(plugin, BlockingService())

    def fail():
        raise OSError("/home/player/private")

    service.diagnostics = fail
    assert asyncio.run(plugin._steam_cleaner_diagnostics()) == {"error": "diagnostics_unavailable"}


def test_real_empty_scan_survives_reload_in_first_report(plugin, monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(main.decky, "DECKY_USER_HOME", str(home), raising=False)
    monkeypatch.setattr(main.decky, "DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path / "settings"))
    state = asyncio.run(plugin.get_steam_cleaner_state())
    assert state["schema_version"] == 1
    assert state["status"] == "idle"
    scan = asyncio.run(plugin.scan_steam_cleaner())
    assert scan["available"] is False
    assert scan["entries"] == []
    assert scan["coverage_complete"] is False
    plugin._close_steam_cleaner_sync()

    reloaded = main.Plugin.__new__(main.Plugin)
    reloaded._init = lambda: None
    stub_other_report_sources(reloaded, monkeypatch)
    try:
        bundle = asyncio.run(reloaded._build_report_bundle([], "", str(home), None))
        diagnostics = bundle["state"]["steam_cleaner"]
        assert diagnostics["events"]
        assert any(event["phase"] == "scan" for event in diagnostics["events"])
        assert reloaded._steam_cleaner.get_state()["scan_id"] is None
        assert reloaded._steam_cleaner.get_state()["status"] == "idle"
    finally:
        reloaded._close_steam_cleaner_sync()
