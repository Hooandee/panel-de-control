"""Wiring: through the normal apply path the fan curve runs off-loop in a worker
thread (no event loop) where a software-loop backend's own start() no-ops. The
Plugin must (re)start that periodic loop ON the event loop AFTER the offloaded
apply confirms the backend is driving — never before (race) and never in auto mode.

Covers startup / lifecycle (_reapply_all) and the fan RPCs.
"""
import asyncio
import concurrent.futures
import importlib
import sys
import threading
import time
import types


def _make_plugin(tmp_path, monkeypatch):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

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

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    p = main.Plugin()
    p._init()
    return p


class _FakeLoopFan:
    """A software-loop-shaped backend: start() must be called ONLY on the event
    loop AND only once the backend is driving (_owns_fan True). Records whether it
    owned the fan at the moment start() fired (proves no race)."""

    def __init__(self):
        self.supported = True
        self._owns = False
        self.start_calls = 0
        self.owned_at_start = []
        self.start_threads = []

    def read_state(self):
        return {"supported": True, "source": "fake-loop", "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if self._owns else 2, "rpm": None, "points": []}]}

    def apply_curve_all(self, points):
        self._owns = True
        return {"ok": True, "detail": "driving"}

    def set_auto(self, _mode):
        self._owns = False
        return {"ok": True, "detail": "released"}

    def restore_auto(self):
        return self.set_auto(None)

    @property
    def _owns_fan(self):
        return self._owns

    def start(self):
        self.start_calls += 1
        self.owned_at_start.append(self._owns)
        self.start_threads.append(threading.get_ident())


async def _wait_for(pred, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.002)
    return pred()


def test_reapply_all_starts_the_loop_after_the_offloaded_apply(tmp_path, monkeypatch):
    """Startup / lifecycle: _reapply_all offloads the curve apply, then the loop
    must be started on the event loop once the apply has driven the fan."""
    p = _make_plugin(tmp_path, monkeypatch)
    fan = _FakeLoopFan()
    p._fan_ctrl = fan
    # A driving profile so _reapply_fans_sync applies a curve (not auto).
    p._fan_curves.set_custom("global", [[40, 30], [60, 50], [80, 90]], None)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def _run():
        loop_tid = threading.get_ident()
        p._reapply_all()  # sync, under a running loop → offloads the apply
        await _wait_for(lambda: fan.start_calls > 0)
        return loop_tid

    loop_tid = asyncio.run(_run())
    ex.shutdown()
    assert fan.start_calls > 0, "the periodic loop was never started"
    assert fan.start_threads == [loop_tid], "start() must run ON the event-loop thread"
    assert all(fan.owned_at_start), "start() fired before the apply drove the fan (race)"


def test_rpc_apply_starts_the_loop_race_free(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch)
    fan = _FakeLoopFan()
    p._fan_ctrl = fan
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def _run():
        await p.set_fan_curve_points([[40, 30], [60, 50], [80, 90]], "global", None)
        await _wait_for(lambda: fan.start_calls > 0)

    asyncio.run(_run())
    ex.shutdown()
    assert fan.start_calls > 0
    assert all(fan.owned_at_start), "loop started before the curve was driven (race)"


def test_auto_mode_does_not_start_a_loop(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch)
    fan = _FakeLoopFan()
    p._fan_ctrl = fan
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = ex

    async def _run():
        await p.set_fan_auto("global", None)     # releases → not driving
        await p._drain_offloaded()
        await asyncio.sleep(0.02)                 # let any done-callback fire

    asyncio.run(_run())
    ex.shutdown()
    assert fan.start_calls == 0, "a loop must not be started in auto mode"
