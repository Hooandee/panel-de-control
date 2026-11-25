import signal

import pytest

import game_force_close
from game_force_close import force_close, game_tree, normalize_appid, process_table

DECK = 1000


class FakeProc:
    """A /proc tree on disk; signals either kill a process or are ignored by it."""

    def __init__(self, root):
        self.root = root
        self.signals = []
        self.ignores_term = set()
        self.ignores_kill = set()
        self.spawn_on_term = None

    def add(self, pid, ppid, name, argv=None, uid=DECK, state="S", start=None):
        base = self.root / str(pid)
        base.mkdir()
        (base / "stat").write_text(
            f"{pid} ({name}) {state} {ppid} " + " ".join(["0"] * 17) + f" {start or pid * 10} 0 0\n"
        )
        (base / "status").write_text(f"Name:\t{name}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (base / "cmdline").write_bytes(b"\0".join(part.encode() for part in (argv or [name])) + b"\0")
        return self

    def remove(self, pid):
        base = self.root / str(pid)
        for child in base.iterdir():
            child.unlink()
        base.rmdir()

    def kill(self, pid, signum):
        self.signals.append((pid, signum))
        if signum == signal.SIGTERM and self.spawn_on_term:
            spawn, self.spawn_on_term = self.spawn_on_term, None
            spawn()
        ignored = self.ignores_term if signum == signal.SIGTERM else self.ignores_kill
        if pid not in ignored:
            self.remove(pid)


@pytest.fixture
def proc(tmp_path):
    fake = FakeProc(tmp_path)
    fake.add(1, 0, "systemd", uid=0)
    fake.add(50, 1, "PluginLoader", uid=0)
    fake.add(60, 50, "python3", uid=0)
    fake.add(100, 1, "gamescope-wl")
    fake.add(200, 100, "steam")
    fake.add(210, 200, "steamwebhelper")
    fake.add(300, 200, "reaper", ["/home/deck/.steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=4049170", "--", "proton", "waitforexitandrun", "game.exe"])
    fake.add(310, 300, "pressure-vessel")
    fake.add(320, 310, "wineserver")
    fake.add(330, 310, "Game.exe")
    fake.add(400, 200, "reaper", ["reaper", "SteamLaunch", "AppId=730", "--", "cs2"])
    fake.add(410, 400, "cs2")
    return fake


def run(proc, appid, **kwargs):
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    return force_close(
        appid, proc_root=proc.root, own_pid=60, kill=proc.kill, sleep=sleep, clock=lambda: now[0], **kwargs,
    )


def test_finds_only_that_games_reaper_tree(proc):
    tree = game_tree(process_table(proc.root), 4049170, own_pid=60)
    assert [process.pid for process in tree] == [300, 310, 320, 330]


def test_an_appid_in_the_games_own_arguments_does_not_match(proc):
    proc.add(500, 200, "reaper", ["reaper", "SteamLaunch", "AppId=10", "--", "tool", "AppId=4049170"])
    assert [process.pid for process in game_tree(process_table(proc.root), 4049170, own_pid=60)] == [300, 310, 320, 330]


def test_never_includes_protected_processes_inside_the_tree(proc):
    proc.add(340, 330, "gamescope")
    proc.add(350, 330, "steamwebhelper")
    proc.add(360, 330, "helper", uid=0)
    proc.add(370, 340, "nested-game")
    pids = [process.pid for process in game_tree(process_table(proc.root), 4049170, own_pid=60)]
    assert 340 not in pids and 350 not in pids and 360 not in pids
    assert 370 in pids


def test_never_touches_panels_own_ancestry(proc):
    proc.add(380, 330, "child")
    proc.add(390, 380, "panel-worker")
    pids = [process.pid for process in game_tree(process_table(proc.root), 4049170, own_pid=390)]
    assert 380 not in pids and 390 not in pids


def test_reports_not_found_without_signalling(proc):
    assert run(proc, 999) == {"result": "not_found", "appid": 999}
    assert proc.signals == []


def test_terminates_with_sigterm_when_the_game_listens(proc):
    result = run(proc, 4049170)
    assert result == {"result": "terminated", "appid": 4049170, "processes": 4}
    assert {signum for _, signum in proc.signals} == {signal.SIGTERM}
    assert (proc.root / "410").exists() and (proc.root / "200").exists() and (proc.root / "210").exists()


def test_escalates_to_sigkill_after_the_grace(proc):
    proc.ignores_term = {330, 320}
    result = run(proc, 4049170)
    assert result == {"result": "killed", "appid": 4049170, "processes": 4, "killed": 2}
    term = [pid for pid, signum in proc.signals if signum == signal.SIGTERM]
    kill = [pid for pid, signum in proc.signals if signum == signal.SIGKILL]
    assert term == [300, 310, 320, 330]
    assert sorted(kill) == [320, 330]


def test_kills_what_the_game_spawned_while_shutting_down(proc):
    proc.ignores_term = {330}
    proc.spawn_on_term = lambda: proc.add(335, 330, "crashpad")
    result = run(proc, 4049170)
    assert result["result"] == "killed"
    assert (335, signal.SIGKILL) in proc.signals


def test_reports_what_survived_sigkill(proc):
    proc.ignores_term = {330}
    proc.ignores_kill = {330}
    result = run(proc, 4049170)
    assert result["result"] == "failed"
    assert result["remaining"] == ["game.exe"]


def test_a_reused_pid_is_not_signalled(proc):
    tree = game_tree(process_table(proc.root), 4049170, own_pid=60)
    proc.remove(330)
    proc.add(330, 1, "Game.exe", start=99999)
    alive = game_force_close._alive(proc.root, next(p for p in tree if p.pid == 330))
    assert alive is False


def test_zombies_count_as_gone(proc):
    proc.ignores_term = {330}
    proc.remove(330)
    proc.add(330, 310, "Game.exe", state="Z")
    assert run(proc, 4049170)["result"] == "terminated"


@pytest.mark.parametrize("value, expected", [
    (4049170, 4049170), ("4049170", 4049170), ((3000000000 << 32) | 0x02000000, 3000000000),
    (0, None), (-1, None), ("abc", None), (True, None), (None, None), ("1" * 21, None),
])
def test_normalizes_app_and_shortcut_ids(value, expected):
    assert normalize_appid(value) == expected


def test_rejects_an_invalid_appid(proc):
    assert run(proc, "x") == {"result": "failed", "code": "invalid_appid"}
