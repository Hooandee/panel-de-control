import gamescope_stats
import os
import time
from gamescope_stats import GamescopeStats


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now

def test_read_exposes_fresh_fps_for_expected_game():
    clock = Clock()
    stats = GamescopeStats(clock=clock, stale_after_s=4)
    stats._apply_line("fps=39.5")
    stats._apply_line("focus=42")

    assert stats.read() == {
        "fps": 39.5,
        "focus": "42",
        "age_s": 0.0,
        "sample_at": 100.0,
        "available": True,
        "reason": "ok",
    }


def test_read_exposes_fresh_fps_from_a_signed_non_steam_renderer():
    stats = GamescopeStats(clock=Clock())
    stats._apply_line("fps=59.8")
    stats._apply_line("focus=-479910431")

    reading = stats.read()

    assert reading["available"] is True
    assert reading["fps"] == 59.8
    assert reading["reason"] == "ok"


def test_read_rejects_stale_fps_instead_of_reusing_it():
    clock = Clock()
    stats = GamescopeStats(clock=clock, stale_after_s=4)
    stats._apply_line("fps=40")
    stats._apply_line("focus=42")
    clock.now = 105.0

    assert stats.read() == {
        "fps": None,
        "focus": "42",
        "age_s": 5.0,
        "sample_at": 100.0,
        "available": False,
        "reason": "fps_stale",
    }


def test_default_stale_window_rejects_six_second_old_fps():
    clock = Clock()
    stats = GamescopeStats(clock=clock)
    stats._apply_line("fps=40")
    stats._apply_line("focus=42")
    clock.now = 106.0

    reading = stats.read()

    assert reading["fps"] is None
    assert reading["reason"] == "fps_stale"


def test_focus_change_clears_previous_games_fps():
    clock = Clock()
    stats = GamescopeStats(clock=clock)
    stats._apply_line("fps=60")
    stats._apply_line("focus=42")
    clock.now = 101.0
    stats._apply_line("fps=45")
    stats._apply_line("focus=99")

    assert stats.read()["fps"] == 45.0
    assert stats.read()["focus"] == "99"
    assert stats.read()["sample_at"] == 101.0


def test_focus_without_a_matching_fps_invalidates_the_previous_sample():
    stats = GamescopeStats(clock=Clock())
    stats._apply_line("fps=60")
    stats._apply_line("focus=42")

    stats._apply_line("focus=99")

    reading = stats.read()
    assert reading["fps"] is None
    assert reading["sample_at"] is None
    assert reading["reason"] == "fps_unavailable"


def test_steam_focus_never_exposes_cached_game_fps():
    stats = GamescopeStats(clock=Clock())
    stats._apply_line("fps=60")
    stats._apply_line("focus=42")
    stats._apply_line("fps=30")
    stats._apply_line("focus=steam")

    reading = stats.read()
    assert reading["fps"] is None
    assert reading["reason"] == "no_game_focus"


def test_missing_fifo_degrades_to_unavailable(tmp_path):
    stats = GamescopeStats(root=str(tmp_path), clock=Clock())

    assert stats._pipe_path() is None
    assert stats.read()["reason"] == "no_game_focus"


def test_pipe_path_finds_dynamic_gamescope_session_directory(tmp_path):
    pipe = tmp_path / "run/user/1000/gamescope.ABC123/stats.pipe"
    pipe.parent.mkdir(parents=True)
    pipe.touch()
    stats = GamescopeStats(root=str(tmp_path), clock=Clock())

    assert stats._pipe_path() == str(pipe)


def test_pipe_path_ignores_a_session_that_disappears_during_discovery(monkeypatch):
    monkeypatch.setattr(
        gamescope_stats.glob,
        "glob",
        lambda _pattern: ["/run/user/1000/gamescope.gone/stats.pipe", "/live"],
    )

    def modified(path):
        if "gone" in path:
            raise FileNotFoundError(path)
        return 10.0

    monkeypatch.setattr(gamescope_stats.os.path, "getmtime", modified)

    assert GamescopeStats(clock=Clock())._pipe_path() == "/live"


def test_invalid_fps_invalidates_the_previous_sample():
    stats = GamescopeStats(clock=Clock())
    stats._apply_line("fps=40")
    stats._apply_line("focus=42")
    stats._apply_line("fps=broken")

    reading = stats.read()
    assert reading["fps"] is None
    assert reading["reason"] == "fps_unavailable"


def test_start_and_stop_are_idempotent():
    stats = GamescopeStats(clock=Clock())

    stats.start()
    first_thread = stats._thread
    stats.start()
    assert stats._thread is first_thread

    stats.stop()
    stats.stop()
    assert stats._stop_event.is_set()


def test_stop_terminates_reader_even_when_fifo_has_no_writer(tmp_path):
    pipe = tmp_path / "run/user/1000/gamescope.test/stats.pipe"
    pipe.parent.mkdir(parents=True)
    os.mkfifo(pipe)
    stats = GamescopeStats(root=str(tmp_path), clock=Clock())

    stats.start()
    deadline = time.monotonic() + 1
    while not stats._thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    stats.stop()

    assert stats._thread is None


def test_stop_discards_samples_from_the_previous_auto_session():
    stats = GamescopeStats(clock=Clock())
    stats._apply_line("fps=60")
    stats._apply_line("focus=42")

    stats.stop()
    reading = stats.read()

    assert reading["available"] is False
    assert reading["reason"] == "no_game_focus"
    assert reading["fps"] is None
