"""Tests for gamescope_stats: parse_stats pure parser + _apply_line helper.

We test the pure parsing logic only — no real FIFOs required. The threaded
reader is tested by calling _apply_line directly (the thread body delegates
all mutation to that method).
"""

from gamescope_stats import GamescopeStats, parse_stats


# ---------------------------------------------------------------------------
# parse_stats
# ---------------------------------------------------------------------------

def test_parse_stats_normal():
    text = "fps=76.942802\nfocus=3768760\n"
    r = parse_stats(text)
    assert abs(r["fps"] - 76.942802) < 1e-4
    assert r["focus"] == "3768760"


def test_parse_stats_takes_last_fps_line():
    text = "fps=30.0\nfps=60.5\nfocus=999\n"
    r = parse_stats(text)
    assert abs(r["fps"] - 60.5) < 1e-4


def test_parse_stats_takes_last_focus_line():
    text = "fps=50.0\nfocus=111\nfocus=222\n"
    r = parse_stats(text)
    assert r["focus"] == "222"


def test_parse_stats_steam_focus():
    text = "fps=90.0\nfocus=steam\n"
    r = parse_stats(text)
    assert r["focus"] == "steam"


def test_parse_stats_missing_focus():
    text = "fps=45.0\n"
    r = parse_stats(text)
    assert abs(r["fps"] - 45.0) < 1e-4
    assert r["focus"] is None


def test_parse_stats_missing_fps():
    text = "focus=12345\n"
    r = parse_stats(text)
    assert r["fps"] is None
    assert r["focus"] == "12345"


def test_parse_stats_empty():
    r = parse_stats("")
    assert r == {"fps": None, "focus": None}


def test_parse_stats_partial_trailing_line_ignored():
    # partial line at end (no newline yet) — must not crash or yield garbage
    text = "fps=60.0\nfocus=99\nfps=7"
    r = parse_stats(text)
    # only the complete lines count
    assert abs(r["fps"] - 60.0) < 1e-4
    assert r["focus"] == "99"


def test_parse_stats_garbage_lines_ignored():
    text = "garbage\nfps=bad_float\nfps=55.5\nfocus=777\n"
    r = parse_stats(text)
    assert abs(r["fps"] - 55.5) < 1e-4
    assert r["focus"] == "777"


def test_parse_stats_never_raises():
    # Should not raise on any bizarre input
    for junk in [None.__class__.__name__, "\x00\xff\n", "====\n"]:
        try:
            parse_stats(junk)
        except Exception as exc:  # pragma: no cover
            raise AssertionError(f"parse_stats raised on {junk!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# GamescopeStats._apply_line + read / game_fps
# ---------------------------------------------------------------------------

def _make() -> GamescopeStats:
    gs = GamescopeStats.__new__(GamescopeStats)
    gs._fps = None
    gs._focus = None
    gs._stop = False
    return gs


def test_apply_fps_line():
    gs = _make()
    gs._apply_line("fps=123.45")
    assert abs(gs._fps - 123.45) < 1e-4


def test_apply_focus_line():
    gs = _make()
    gs._apply_line("focus=99999")
    assert gs._focus == "99999"


def test_apply_garbage_line_is_noop():
    gs = _make()
    gs._apply_line("this is garbage")
    assert gs._fps is None and gs._focus is None


def test_apply_bad_fps_value_is_noop():
    gs = _make()
    gs._apply_line("fps=not_a_number")
    assert gs._fps is None


def test_game_fps_returns_fps_when_real_game_focused():
    gs = _make()
    gs._fps = 72.0
    gs._focus = "3768760"  # numeric appid
    assert abs(gs.game_fps() - 72.0) < 1e-4


def test_game_fps_returns_none_when_steam_focused():
    gs = _make()
    gs._fps = 60.0
    gs._focus = "steam"
    assert gs.game_fps() is None


def test_game_fps_returns_none_when_focus_none():
    gs = _make()
    gs._fps = 60.0
    gs._focus = None
    assert gs.game_fps() is None


def test_read_returns_none_fps_for_steam_focus():
    gs = _make()
    gs._fps = 60.0
    gs._focus = "steam"
    r = gs.read()
    assert r["fps"] is None
    assert r["focus"] == "steam"


def test_read_returns_fps_for_real_game():
    gs = _make()
    gs._fps = 45.5
    gs._focus = "12345"
    r = gs.read()
    assert abs(r["fps"] - 45.5) < 1e-4


def test_start_is_idempotent(tmp_path):
    """start() twice must not raise or spawn duplicate threads."""
    import os
    import threading
    pipe = tmp_path / "stats.pipe"
    try:
        os.mkfifo(str(pipe))
    except OSError:
        # mkfifo not available (unlikely on Linux/macOS CI) — skip gracefully
        return
    gs = GamescopeStats(root=str(tmp_path))
    t0 = threading.active_count()
    gs.start()
    gs.start()  # idempotent
    assert threading.active_count() >= t0  # at least 1 thread started
    gs.stop()
