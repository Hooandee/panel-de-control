import asyncio
import signal
import sys

import pytest

from game_freeze import MAX_MS, GameFreezer, game_processes
from test_game_force_close import FakeProc
from test_tdp_guard_rpc import plugin  # noqa: F401


@pytest.fixture
def proc(tmp_path):
    fake = FakeProc(tmp_path)
    fake.add(1, 0, "systemd", uid=0)
    fake.add(100, 1, "gamescope-wl")
    fake.add(200, 100, "steam")
    fake.add(210, 200, "steamwebhelper")
    fake.add(300, 200, "reaper", ["/home/deck/.steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=292030", "--", "proton", "witcher3.exe"])
    fake.add(310, 300, "pv-adverb")
    fake.add(320, 310, "wineserver")
    fake.add(330, 310, "MainThread", ["witcher3.exe"])
    fake.add(400, 200, "reaper", ["reaper", "SteamLaunch", "AppId=730", "--", "cs2"])
    fake.add(410, 400, "cs2")
    return fake


class Harness:
    def __init__(self, proc):
        self.proc = proc
        self.signals = []
        self.timers = []
        self.cancelled = []
        self.events = []
        self.freezer = GameFreezer(
            schedule=lambda delay, run: self.timers.append((delay, run)) or len(self.timers),
            cancel=self.cancelled.append,
            kill=lambda pid, sig: self.signals.append((pid, sig)),
            find=lambda appid: game_processes(appid, proc.root),
            proc_root=proc.root,
            on_change=lambda event, fields: self.events.append((event, fields)),
        )


def test_freezes_only_that_games_tree_and_never_its_reaper_or_steam(proc):
    assert [process.pid for process in game_processes(292030, proc.root)] == [310, 320, 330]
    assert game_processes(99, proc.root) == []


def test_pause_stops_the_game_and_always_schedules_a_thaw(proc):
    h = Harness(proc)
    assert h.freezer.pause(292030, 600) is True
    assert h.signals == [(310, signal.SIGSTOP), (320, signal.SIGSTOP), (330, signal.SIGSTOP)]
    delay, run = h.timers[-1]
    assert delay == 0.6
    run()
    assert sorted(h.signals[3:]) == [(310, signal.SIGCONT), (320, signal.SIGCONT), (330, signal.SIGCONT)]
    assert h.freezer.frozen is False
    assert [event for event, _ in h.events] == ["freeze", "thaw"]


def test_a_renewal_only_moves_the_deadline(proc):
    h = Harness(proc)
    h.freezer.pause(292030, 1000)
    h.freezer.pause(292030, 1000)
    assert len([s for s in h.signals if s[1] == signal.SIGSTOP]) == 3
    assert h.cancelled == [1]
    assert [event for event, _ in h.events] == ["freeze"]


def test_a_freeze_never_outlasts_the_cap(proc):
    h = Harness(proc)
    h.freezer.pause(292030, 60_000)
    assert h.timers[-1][0] == MAX_MS / 1000


def test_another_game_thaws_the_first(proc):
    h = Harness(proc)
    h.freezer.pause(292030, 1000)
    h.freezer.pause(730, 1000)
    assert (410, signal.SIGSTOP) in h.signals
    assert all((pid, signal.SIGCONT) in h.signals for pid in (310, 320, 330))


def test_a_pid_reused_meanwhile_is_not_woken(proc):
    h = Harness(proc)
    h.freezer.pause(292030, 1000)
    proc.remove(330)
    proc.add(330, 1, "someone-else", start=999999)
    h.freezer.resume()
    assert (330, signal.SIGCONT) not in h.signals
    assert (320, signal.SIGCONT) in h.signals


def test_shortcut_ids_and_bad_input(proc):
    h = Harness(proc)
    assert h.freezer.pause(str(292030 << 32), 500) is True
    h.freezer.resume()
    for appid, ms in ((0, 500), ("x", 500), (292030, True), (292030, "500")):
        assert h.freezer.pause(appid, ms) is False


def test_nothing_to_freeze_reports_false_and_schedules_nothing(proc):
    h = Harness(proc)
    assert h.freezer.pause(99, 500) is False
    assert h.timers == []
    h.freezer.resume()
    assert h.events == []



def test_arm_handhelds_are_not_frozen_until_validated(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(main.device_tree, "is_arm", lambda: True)
    monkeypatch.setattr(main.game_freeze.GameFreezer, "pause", lambda *_: pytest.fail("froze on ARM"))
    plugin._freeze_on_arm = None
    assert asyncio.run(plugin.pause_theme_game(292030, 1000)) is False
