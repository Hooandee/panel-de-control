import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from test_tdp_guard_rpc import plugin  # noqa: F401


def test_start_is_idempotent_and_shutdown_cannot_restart(plugin, monkeypatch):  # noqa: F811
    main = sys.modules['main']
    service = SimpleNamespace(start=Mock(), stop=AsyncMock(), state=lambda: {'status': 'ready'})
    factory = Mock(return_value=service)
    monkeypatch.setattr(main, 'SteamInventoryCompat', factory, raising=False)
    plugin._start_steam_inventory_compat()
    plugin._start_steam_inventory_compat()
    assert factory.call_count == 1
    assert service.start.call_count == 1
    assert plugin._support_steam_inventory() == {'status': 'ready'}
    asyncio.run(plugin._stop_steam_inventory_compat())
    service.stop.assert_awaited_once()
    plugin._shutting_down = True
    plugin._start_steam_inventory_compat()
    assert service.start.call_count == 1


def test_not_started_support_state_and_stop_are_safe(plugin):  # noqa: F811
    assert plugin._support_steam_inventory()['status'] == 'stopped'
    asyncio.run(plugin._stop_steam_inventory_compat())


def test_inventory_cleanup_cannot_suspend_before_critical_handoff(plugin, monkeypatch):  # noqa: F811
    main = sys.modules['main']
    monkeypatch.setattr(main.fan_expose, 'remove_conf', Mock())
    for method in ('_stop_pulse', '_prepare_shutdown', '_shutdown_apply_executor',
                   '_shutdown_controller_action_executor', '_finish_theme_shutdown_sync', '_stop_journal'):
        monkeypatch.setattr(plugin, method, Mock())
    monkeypatch.setattr(plugin, '_drain_offloaded_sync', Mock(return_value=True))
    monkeypatch.setattr(plugin, '_stop_kiosk', AsyncMock())
    monkeypatch.setattr(plugin, '_stop_remote_access', AsyncMock())
    plugin._screen_sleep = None
    for operation in ('_unload', '_uninstall'):
        events = []
        monkeypatch.setattr(plugin, '_perform_shutdown_handoff', lambda reason: events.append('handoff'))

        async def stop_inventory():
            events.append('inventory')
            await asyncio.sleep(0)

        monkeypatch.setattr(plugin, '_stop_steam_inventory_compat', stop_inventory)
        unloading = getattr(plugin, operation)()
        try:
            unloading.send(None)
            assert events == ['handoff', 'inventory']
        finally:
            unloading.close()
