import asyncio
import concurrent.futures
import importlib
import threading
import time
import types

import pytest

from test_event_loop_offload import _make_plugin, _NeverCompletingExecutor

_BUDGET_S = 2.0


class _HangingScreen:
    asleep = True
    detail = "test"

    def __init__(self, release):
        self._release = release
        self.calls = []

    def close(self):
        self.calls.append(False)
        self._release.wait(timeout=10)
        return True


class _HangingAsyncService:
    def __init__(self, release):
        self._release = release
        self.terminated = False
        self.released = False

    def terminate_now(self):
        self.terminated = True

    def release_hardware(self):
        self.released = True
        self._release.wait(timeout=10)

    async def shutdown(self):
        await asyncio.sleep(10)


def _hang_everything(p, monkeypatch, release):
    main = importlib.import_module("main")
    hang = lambda *_args, **_kwargs: release.wait(timeout=10) or True  # noqa: E731

    p._screen_sleep = _HangingScreen(release)
    p._eco_watch_task = None
    p._kiosk = _HangingAsyncService(release)
    p._kiosk_task = None
    p._remote_access = _HangingAsyncService(release)
    p._apply_executor = _NeverCompletingExecutor()

    p._restore_fans_safe = hang
    p._restore_color_safe = hang
    p._restore_audio_safe = hang
    p._release_cpu_controls_sync = hang
    p._release_gpu_clock_sync = hang
    p._restore_power_handoff = hang
    monkeypatch.setattr(main.fan_expose, "remove_conf", hang)

    theme_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    theme_executor.submit(hang)
    p._theme_executor = theme_executor

    cleaner_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._steam_cleaner_executor = cleaner_executor
    p._steam_cleaner = None
    p._steam_cleaner_closed = False
    p._steam_cleaner_init_future = cleaner_executor.submit(hang)

    hud_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    coordinator = getattr(p, "_hud_coordinator", None)
    if coordinator is not None:
        coordinator._executor = hud_executor
    p._restore_hud_safe = hang
    return [theme_executor, cleaner_executor, hud_executor]


@pytest.mark.parametrize("method", ("_unload", "_uninstall"))
def test_shutdown_finishes_within_budget_when_every_stage_hangs(
    tmp_path, monkeypatch, method,
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    release = threading.Event()
    executors = _hang_everything(p, monkeypatch, release)

    before = time.monotonic()
    try:
        asyncio.run(getattr(p, method)())
        elapsed = time.monotonic() - before
    finally:
        release.set()
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)

    assert elapsed < _BUDGET_S


def test_unload_still_wakes_the_screen_and_attempts_every_handoff(
    tmp_path, monkeypatch,
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    release = threading.Event()
    executors = _hang_everything(p, monkeypatch, release)
    release.set()
    events = []
    p._restore_fans_safe = lambda: events.append("fans")
    p._restore_power_handoff = lambda **_kwargs: events.append("power") or True

    try:
        asyncio.run(p._unload())
    finally:
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)

    assert p._screen_sleep.calls == [False]
    assert events[:1] == ["fans"] and "power" in events


def test_shutdown_drain_fits_inside_the_budget():
    main = importlib.import_module("main")

    assert main._SHUTDOWN_DRAIN_TIMEOUT_S < main._SHUTDOWN_BUDGET_S < _BUDGET_S


def test_unload_without_async_services_never_suspends(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._screen_sleep = types.SimpleNamespace(asleep=False, close=lambda: True)
    p._eco_watch_task = None
    p._kiosk = None
    p._remote_access = None

    unload = p._unload()
    with pytest.raises(StopIteration):
        unload.send(None)


def test_unload_then_uninstall_stays_bounded_and_never_doubles_the_handoff(
    tmp_path, monkeypatch,
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    release = threading.Event()
    executors = _hang_everything(p, monkeypatch, release)
    starts = []
    p._restore_fans_safe = lambda: starts.append("fans") or release.wait(timeout=10)

    try:
        before = time.monotonic()
        asyncio.run(p._unload())
        unload_s = time.monotonic() - before
        before = time.monotonic()
        asyncio.run(p._uninstall())
        uninstall_s = time.monotonic() - before
    finally:
        release.set()
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)

    assert unload_s < _BUDGET_S and uninstall_s < _BUDGET_S
    assert starts == ["fans"]


def test_unload_signals_the_ssh_server_and_releases_the_kiosk_even_when_stalled(
    tmp_path, monkeypatch,
):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    release = threading.Event()
    executors = _hang_everything(p, monkeypatch, release)

    try:
        asyncio.run(p._unload())
    finally:
        release.set()
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)

    assert p._remote_access.terminated
    assert p._kiosk.released
