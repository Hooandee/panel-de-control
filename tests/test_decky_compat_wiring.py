import asyncio
import sys
import types


if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER = "deck"
    decky.DECKY_VERSION = "v3.2.8"
    decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    sys.modules["decky"] = decky

import main


def _plugin():
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._decky_compat_task = None
    return plugin


def test_unaffected_decky_version_does_not_start_recovery_task(monkeypatch):
    plugin = _plugin()
    monkeypatch.setattr(main.decky, "DECKY_VERSION", "v3.2.8", raising=False)

    async def run():
        plugin._start_decky_frontend_compat()
        await asyncio.sleep(0)

    asyncio.run(run())

    assert plugin._decky_compat_task is None


def test_326_starts_one_recovery_task(monkeypatch):
    plugin = _plugin()
    calls = []
    monkeypatch.setattr(main.decky, "DECKY_VERSION", "v3.2.6", raising=False)

    async def recover(version):
        calls.append(version)
        return main.decky_compat.RecoveryResult("recovered", attempted=True)

    monkeypatch.setattr(main.decky_compat, "recover_frontend", recover)

    async def run():
        plugin._start_decky_frontend_compat()
        task = plugin._decky_compat_task
        plugin._start_decky_frontend_compat()
        assert plugin._decky_compat_task is task
        await task
        await asyncio.sleep(0)

    asyncio.run(run())

    assert calls == ["v3.2.6"]
    assert plugin._decky_compat_task is None


def test_shutdown_cancels_pending_recovery(monkeypatch):
    plugin = _plugin()
    started = asyncio.Event()
    monkeypatch.setattr(main.decky, "DECKY_VERSION", "v3.2.6", raising=False)

    async def recover(_version):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(main.decky_compat, "recover_frontend", recover)

    async def run():
        plugin._start_decky_frontend_compat()
        task = plugin._decky_compat_task
        await started.wait()
        plugin._stop_decky_frontend_compat()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return task

    task = asyncio.run(run())

    assert task.cancelled()
    assert plugin._decky_compat_task is None
