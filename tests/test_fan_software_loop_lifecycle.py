"""The periodic re-assert loop of the software-loop backends, exercised for real
against an event loop. Covers: the loop starts under a running loop and re-evaluates
the curve as temperature changes; the per-tick blocking work (temp read + target
write) runs OFF the event-loop thread; the Legion Go S high-temp guardian fires
THROUGH the loop; and set_auto stops the loop and releases. Fake temp_fn + fake EC,
so no hardware is touched and the cadence is sped up via _LOOP_INTERVAL."""
import asyncio
import threading
import time

import pytest

import fans.software_loop as sl
from fans.legion_ec import (
    LegionGoSFanBackend,
    REG_OVERRIDE,
    _GOS_MAX_RPM,
    _GOS_TEMP_GUARD_C,
)


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


class FakeEC:
    """Dict-backed EC that records the thread each write ran on."""

    def __init__(self):
        self.mem = {}
        self.write_threads = []

    def read(self, addr):
        return self.mem.get(addr, 0)

    def write(self, addr, val):
        self.mem[addr] = val & 0xFF
        self.write_threads.append(threading.get_ident())
        return True  # mirror _PortEC.write (True on success)


def _dmi_gos(root, name="83N6", family="Legion Go S 8APU1"):
    import os
    d = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(d, exist_ok=True)
    for attr, val in (("product_name", name), ("product_family", family), ("product_version", "")):
        with open(os.path.join(d, attr), "w") as f:
            f.write(val)


def _override(ec):
    return (ec.read(REG_OVERRIDE + 1) << 8) | ec.read(REG_OVERRIDE)


async def _wait_for(pred, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.002)
    return pred()


@pytest.fixture
def fast_loop(monkeypatch):
    # Tick often so the test doesn't wait the production 1.5 s cadence.
    monkeypatch.setattr(sl, "_LOOP_INTERVAL", 0.005)


def _gos(tmp_path, ec, temp_ref):
    _dmi_gos(str(tmp_path))
    return LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: temp_ref["v"])


def test_loop_reevaluates_curve_as_temperature_rises(tmp_path, fast_loop):
    ec = FakeEC()
    temp = {"v": 50.0}
    b = _gos(tmp_path, ec, temp)

    async def _run():
        b.apply_curve_all(CURVE)  # under a running loop → loop starts
        assert b._task is not None
        await _wait_for(lambda: _override(ec) == b.target_for_temp(50.0))
        cool = _override(ec)
        temp["v"] = 85.0  # hotter → the curve maps to a higher target
        ok = await _wait_for(lambda: _override(ec) == b.target_for_temp(85.0))
        assert ok, f"loop never tracked the new temp (stuck at {_override(ec)})"
        assert _override(ec) > cool
        b.set_auto(None)

    asyncio.run(_run())


def test_tick_runs_off_the_event_loop_thread(tmp_path, fast_loop):
    ec = FakeEC()
    temp = {"v": 70.0}
    b = _gos(tmp_path, ec, temp)

    async def _run():
        loop_tid = threading.get_ident()
        b.apply_curve_all(CURVE)   # starts the loop
        ec.write_threads.clear()   # drop the immediate synchronous apply's write
        # Wait for at least one loop-driven tick to write, then snapshot BEFORE the
        # release (set_auto's synchronous _release write is a separate path).
        await _wait_for(lambda: bool(ec.write_threads))
        tick_threads = list(ec.write_threads)
        b.set_auto(None)
        return loop_tid, tick_threads

    loop_tid, tick_threads = asyncio.run(_run())
    assert tick_threads, "the loop never wrote a target"
    assert loop_tid not in tick_threads, "the per-tick EC write ran ON the event loop"


def test_guardian_forces_max_through_the_loop(tmp_path, fast_loop):
    ec = FakeEC()
    temp = {"v": 55.0}  # gentle: curve maps well below the cap
    b = _gos(tmp_path, ec, temp)

    async def _run():
        b.apply_curve_all(CURVE)
        await _wait_for(lambda: _override(ec) == b.target_for_temp(55.0))
        assert _override(ec) < _GOS_MAX_RPM  # not yet at the cap
        temp["v"] = _GOS_TEMP_GUARD_C + 5  # cross the guardian
        ok = await _wait_for(lambda: _override(ec) == _GOS_MAX_RPM)
        assert ok, "guardian never forced the capped max through the loop"
        b.set_auto(None)

    asyncio.run(_run())


def test_release_overrides_an_in_flight_tick_write(tmp_path):
    """A tick's write runs off-loop, concurrently with a release. The release must
    WIN — a tick that is mid-write must never resurrect the override after set_auto
    hands the fan back to firmware (else we'd report auto while still driving)."""
    from fans.control import sanitize_curve

    _dmi_gos(str(tmp_path))
    entered = threading.Event()
    proceed = threading.Event()

    class BlockingEC(FakeEC):
        def __init__(self):
            super().__init__()
            self.block_next = False

        def write(self, addr, val):
            if self.block_next:
                self.block_next = False
                entered.set()
                proceed.wait(2.0)  # hold the tick mid-write
            return super().write(addr, val)

    ec = BlockingEC()
    b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
    b._points = [list(p) for p in sanitize_curve(CURVE)]  # driving; no loop task
    ec.block_next = True
    tick = threading.Thread(target=b._apply_once)   # a tick, blocks mid non-zero write
    tick.start()
    assert entered.wait(2.0), "tick never reached its write"
    releaser = threading.Thread(target=lambda: b.set_auto(None))
    releaser.start()
    time.sleep(0.05)      # let set_auto reach (and block on) the release
    proceed.set()         # unblock the tick's write
    tick.join(2.0)
    releaser.join(2.0)
    assert _override(ec) == 0, "a stale tick write survived the release"


def test_stop_off_loop_marshals_cancel_via_call_soon_threadsafe(tmp_path, fast_loop):
    # set_auto runs in a worker thread; Task.cancel() from off-loop must be marshalled
    # onto the loop (call_soon_threadsafe), never called directly (loop corruption).
    ec = FakeEC()
    b = _gos(tmp_path, ec, {"v": 70.0})

    async def _run():
        b.apply_curve_all(CURVE)
        assert b._task is not None
        loop = asyncio.get_running_loop()
        calls = []
        orig = loop.call_soon_threadsafe
        loop.call_soon_threadsafe = lambda cb, *a: (calls.append(cb), orig(cb, *a))[1]
        await asyncio.to_thread(b.stop)
        await asyncio.sleep(0.03)
        assert calls, "off-loop stop must use call_soon_threadsafe"

    asyncio.run(_run())


def test_stop_on_loop_cancels_directly(tmp_path, fast_loop):
    ec = FakeEC()
    b = _gos(tmp_path, ec, {"v": 70.0})

    async def _run():
        b.apply_curve_all(CURVE)
        task = b._task
        b.stop()  # on the loop thread
        await asyncio.sleep(0.02)
        assert task.cancelled() or task.done()

    asyncio.run(_run())


def test_set_auto_stops_the_loop_and_releases(tmp_path, fast_loop):
    ec = FakeEC()
    temp = {"v": 70.0}
    b = _gos(tmp_path, ec, temp)

    async def _run():
        b.apply_curve_all(CURVE)
        assert b._task is not None
        b.set_auto(None)
        assert b._task is None            # loop stopped
        await asyncio.sleep(0.03)         # let any in-flight tick settle
        assert _override(ec) == 0         # released to firmware
        # No write may resurrect the override after release.
        await asyncio.sleep(0.03)
        assert _override(ec) == 0

    asyncio.run(_run())
