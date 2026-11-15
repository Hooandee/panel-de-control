"""RPC-level tests for download mode (eco): override + restore + manual clear."""
import asyncio
import sys
import types
from main_harness import fake_decky, load_main


class _FakeToggle:
    def __init__(self, supported=True, on=True):
        self.supported = supported
        self._on = on

    def enabled(self):
        return self._on if self.supported else False

    def set(self, enabled):
        if not self.supported:
            return False
        self._on = bool(enabled)
        return True


def _make_plugin(tmp_path, monkeypatch, boost=None):
    fake_decky(monkeypatch, tmp_path)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = True
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=20)

        def level_limits(self):
            return {}

        def set_tdp(self, w, ac):
            return TdpResult(w, w, True, "")

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": False)
    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": False, raising=False)
    monkeypatch.setattr(main, "_ECO_INPUT_POLL_S", 0.01)

    if boost is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            self._boost = boost

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin()


def test_manual_tdp_change_clears_eco(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    asyncio.run(p.set_eco(True, 40))
    assert p._settings["eco_enabled"] is True
    asyncio.run(p.set_tdp_watts(18, "global", None))
    assert p._settings["eco_enabled"] is False  # manual control exits eco


def test_manual_boost_change_clears_eco(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, boost=boost)
    asyncio.run(p.set_eco(True, 40))
    asyncio.run(p.set_cpu_boost(True))
    assert p._settings["eco_enabled"] is False
    assert boost.enabled() is True


class _FakeScreen:
    """`fails` wakes fail before one succeeds; `confirm_sleep=False` leaves a sleep unproven."""

    def __init__(self, confirm_sleep=True, fails=0, gate=None):
        self.supported, self.asleep, self.detail, self.version = True, False, "ok", None
        self.confirm_sleep, self.fails, self.gate, self.calls = confirm_sleep, fails, gate, []

    def probe(self):
        return True

    def set(self, asleep):
        self.calls.append(asleep)
        if asleep and self.gate:
            self.gate.wait(2)
        if not asleep and self.fails:
            self.fails -= 1
            return False
        self.asleep = asleep
        return self.confirm_sleep or not asleep


class _FakeInput:
    def __init__(self):
        self.sources, self.opened, self.closed = [], 0, 0

    def open(self):
        self.opened += 1
        return 1

    def close(self):
        self.closed += 1

    def wait(self, timeout):
        import time
        time.sleep(timeout)
        return self.sources.pop(0) if self.sources else None


def _setup(tmp_path, monkeypatch, screen=None):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    p._init()
    p._screen_sleep, p._input_wake = screen or _FakeScreen(), _FakeInput()
    main = sys.modules["main"]
    monkeypatch.setattr(main, "_SCREEN_WAKE_RETRY_S", 0.01)
    emitted = []

    async def emit(event, *args):
        emitted.append(event)

    monkeypatch.setattr(main, "_emit_to_frontend", emit)
    return p, p._screen_sleep, emitted


async def _until(predicate, timeout=2.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end
        await asyncio.sleep(0.01)


async def _leave(p):
    await p.set_eco(False, 50)
    await asyncio.wait_for(p._eco_watch_task, 2)


def test_screen_state_and_refusal_outside_download_mode(tmp_path, monkeypatch):
    p, screen, _ = _setup(tmp_path, monkeypatch)
    st = asyncio.run(p.get_eco_state())
    assert st["screen_off"] is True and st["screen_asleep"] is False
    assert asyncio.run(p.set_eco_screen(True)) == {"ok": False, "asleep": False}
    assert screen.calls == []


def test_unconfirmed_sleep_is_undone(tmp_path, monkeypatch):
    p, screen, _ = _setup(tmp_path, monkeypatch, _FakeScreen(confirm_sleep=False))

    async def run():
        await p.set_eco(True, 50)
        r = await p.set_eco_screen(True)
        await _leave(p)
        return r

    assert asyncio.run(run()) == {"ok": False, "asleep": False}
    assert screen.calls == [True, False]


def test_raw_input_lights_the_panel_and_tells_the_frontend(tmp_path, monkeypatch):
    p, screen, emitted = _setup(tmp_path, monkeypatch)

    async def run():
        await p.set_eco(True, 50)
        await p.set_eco_screen(True)
        p._input_wake.sources.append("FTS3528")
        await _until(lambda: emitted)
        await _leave(p)

    asyncio.run(run())
    assert screen.calls == [True, False] and emitted == ["pdc_eco_input"]
    assert p._input_wake.closed >= 1


def test_failed_wake_after_leaving_download_mode_is_retried(tmp_path, monkeypatch):
    p, screen, _ = _setup(tmp_path, monkeypatch, _FakeScreen(fails=2))

    async def run():
        await p.set_eco(True, 50)
        await p.set_eco_screen(True)
        await _leave(p)

    asyncio.run(run())
    assert screen.calls == [True, False, False, False] and not screen.asleep


def test_wake_arriving_while_a_sleep_is_in_flight_wins(tmp_path, monkeypatch):
    import threading
    gate = threading.Event()
    p, screen, _ = _setup(tmp_path, monkeypatch, _FakeScreen(gate=gate))

    async def run():
        await p.set_eco(True, 50)
        sleeping = asyncio.create_task(p.set_eco_screen(True))
        await _until(lambda: screen.calls)
        waking = asyncio.create_task(p.set_eco_screen(False))
        await asyncio.sleep(0.05)
        gate.set()
        await sleeping
        woke = await waking
        await _leave(p)
        return woke

    assert asyncio.run(run()) == {"ok": True, "asleep": False}
    assert screen.calls == [True, False]


def test_eco_diagnostic_failure_does_not_prevent_toggle(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    main = sys.modules['main']
    records = []
    monkeypatch.setattr(main.journal, 'active', types.SimpleNamespace(write=lambda *a, **k: records.append((a, k))))
    def unavailable():
        raise OSError('unavailable')
    monkeypatch.setattr(main.pulse, 'performance_sample', unavailable)
    result = asyncio.run(p.set_eco(True, 50))
    assert result['enabled'] is True
    record = next(k for a, k in records if a[:3] == ('INFO', 'eco', 'transition_readback'))
    assert record['before'] == {'error': 'OSError'} and record['after'] == {'error': 'OSError'}


def test_manual_controls_cancel_pending_eco_activation(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    p._init()
    main = sys.modules['main']
    monkeypatch.setattr(main.journal, 'active', types.SimpleNamespace(write=lambda *a, **k: None))
    async def scenario(clear):
        pending = asyncio.get_running_loop().create_future()
        entered = asyncio.Event()
        async def readback():
            entered.set()
            return await pending
        monkeypatch.setattr(p, '_eco_performance_readback', readback)
        activation = asyncio.create_task(p.set_eco(True, 50))
        await entered.wait()
        clear()
        pending.set_result({'boost': 1})
        assert (await activation)['enabled'] is False
    for clear in (p._clear_eco, p._exit_eco_for_cpu):
        asyncio.run(scenario(clear))


def test_eco_readback_timeout_is_reported_without_waiting_for_hardware(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    main = sys.modules['main']
    async def stuck(*args, **kwargs):
        await asyncio.Event().wait()
    monkeypatch.setattr(main.asyncio, 'to_thread', stuck)
    monkeypatch.setattr(main, '_ECO_READBACK_TIMEOUT_S', 0.01)
    async def scenario():
        result = await asyncio.wait_for(p._eco_performance_readback(), timeout=1.5)
        assert result == {'error': 'TimeoutError'}
    asyncio.run(scenario())
