"""SMT and physical-core restrictions share the resume protection window."""
import asyncio
from pathlib import Path

import pytest

from tests.test_cpu_rpc import _FakeCores, _FakeFrequency, _FakeToggle, _make_plugin


class _Smt(_FakeToggle):
    def __init__(self):
        super().__init__(on=False)
        self.writes = []

    def set(self, enabled):
        self.writes.append(bool(enabled))
        return super().set(enabled)


class _Guard:
    ready = False
    last_error = None

    def ensure(self):
        self.ready = True
        return True

    def diagnostics(self):
        return {"installed": self.ready, "loaded": self.ready, "last_error": None}


def _plugin(tmp_path, monkeypatch, cores=4):
    import sys
    smt = _Smt()
    plugin = _make_plugin(tmp_path, monkeypatch, smt=smt, boost=_FakeToggle(),
                          cores=_FakeCores(active=cores), frequency=_FakeFrequency())
    monkeypatch.setattr(sys.modules['main'], 'SleepCoreGuard', _Guard)
    plugin._init()
    plugin._cpu_profiles.set_cores('global', cores)
    plugin._cpu_profiles.set_smt('global', False)
    return plugin, smt


async def _apply(plugin):
    plugin._apply_cpu()
    await plugin._offload_call(lambda: None)


@pytest.mark.parametrize('cores', [4, 8])
def test_smt_off_installs_sleep_guard_even_with_all_physical_cores(tmp_path, monkeypatch, cores):
    plugin, _ = _plugin(tmp_path, monkeypatch, cores)
    plugin._guard_sleep_with_cores_off()
    assert plugin._sleep_core_guard.ready


@pytest.mark.parametrize('cores', [4, 8])
def test_resume_holds_smt_without_persisting_temporary_state(tmp_path, monkeypatch, cores):
    plugin, smt = _plugin(tmp_path, monkeypatch, cores)
    path = Path(plugin._cpu_profiles._path)
    baseline = path.read_bytes()

    async def scenario():
        plugin._on_resume_detected(10)
        await _apply(plugin)
        assert smt.enabled() and plugin._cores.active() == 8
        assert plugin._cpu_state()['smt']['enabled'] is True
        diagnostics = plugin._resume_hold_diagnostics()
        assert diagnostics['active'] and any(event.get('what') == 'smt' for event in diagnostics['history'])
        assert path.read_bytes() == baseline
        assert plugin._cpu_profiles.effective(None)['smt'] is False
        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert smt.enabled() is False and plugin._cores.active() == cores
        assert smt.writes == [True, False]
        assert path.read_bytes() == baseline

    asyncio.run(scenario())


@pytest.mark.parametrize('action', ['cores', 'smt'])
def test_explicit_change_overrides_only_its_field_until_next_resume(tmp_path, monkeypatch, action):
    plugin, smt = _plugin(tmp_path, monkeypatch)

    async def scenario():
        plugin._on_resume_detected(10)
        await _apply(plugin)
        if action == 'cores':
            await plugin.set_active_cores(6)
        else:
            await plugin.set_smt(False)
        await _apply(plugin)
        assert plugin._cores.active() == (6 if action == 'cores' else 8)
        assert smt.enabled() is (action == 'cores')
        assert plugin._resume_hold_diagnostics()['overridden'] == [action]
        old = plugin._resume_token
        plugin._on_resume_detected(10)
        plugin._release_resume_hold(old)
        await _apply(plugin)
        assert plugin._resume_hold_active()
        assert smt.enabled() and plugin._cores.active() == 8
        assert plugin._resume_hold_diagnostics()['overridden'] == []
        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert smt.enabled() is False
        assert plugin._cores.active() == (6 if action == 'cores' else 4)

    asyncio.run(scenario())


def test_release_reads_current_game_intent_and_preserves_both_profiles(tmp_path, monkeypatch):
    plugin, smt = _plugin(tmp_path, monkeypatch)
    profiles = plugin._cpu_profiles
    profiles.set_cores('game', 6, appid='42')
    profiles.set_smt('game', True, appid='42')
    baseline = Path(profiles._path).read_bytes()

    async def scenario():
        plugin._on_resume_detected(10)
        await _apply(plugin)
        plugin._current_appid = '42'
        await _apply(plugin)
        assert smt.enabled() and plugin._cores.active() == 8
        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert smt.enabled() and plugin._cores.active() == 6
        assert profiles.effective(None)['smt'] is False
        assert profiles.effective(None)['cores'] == 4
        assert profiles.effective('42')['smt'] is True
        assert Path(profiles._path).read_bytes() == baseline

    asyncio.run(scenario())


def test_shutdown_cancels_release_without_reapplying_restrictions(tmp_path, monkeypatch):
    plugin, smt = _plugin(tmp_path, monkeypatch)

    async def scenario():
        plugin._on_resume_detected(10)
        await _apply(plugin)
        plugin._shutting_down = True
        plugin._release_resume_hold(plugin._resume_token)
        assert not plugin._resume_hold_active()
        assert smt.enabled() and plugin._cores.active() == 8
        assert smt.writes == [True]

    asyncio.run(scenario())


def test_manual_override_does_not_leak_into_another_game(tmp_path, monkeypatch):
    plugin, smt = _plugin(tmp_path, monkeypatch)
    profiles = plugin._cpu_profiles
    profiles.set_cores('game', 6, appid='42')
    profiles.set_smt('game', False, appid='42')

    async def scenario():
        plugin._on_resume_detected(10)
        await _apply(plugin)
        await plugin.set_smt(False)
        assert smt.enabled() is False
        plugin._current_appid = '42'
        await _apply(plugin)
        assert smt.enabled() and plugin._cores.active() == 8
        assert plugin._resume_hold_diagnostics()['overridden'] == []
        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert smt.enabled() is False and plugin._cores.active() == 6
        assert profiles.effective(None)['cores'] == 4
        assert profiles.effective('42')['cores'] == 6

    asyncio.run(scenario())


def test_queued_profile_cannot_park_threads_after_resume_detection(tmp_path, monkeypatch):
    import threading

    plugin, smt = _plugin(tmp_path, monkeypatch)
    unblock = threading.Event()

    async def scenario():
        plugin._offload(unblock.wait)
        try:
            plugin._apply_cpu()
            # The sleep service leaves all threads online before the worker resumes.
            smt.set(True)
            plugin._cores.set(8)
            plugin._on_resume_detected(42.6)
        finally:
            unblock.set()
        await plugin._offload_call(lambda: None)
        assert smt.enabled() and plugin._cores.active() == 8
        await _apply(plugin)
        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert not smt.enabled() and plugin._cores.active() == 4

    asyncio.run(scenario())
