from display.night import clamp_minute, is_night_active
from display.night_store import NightStore

# ---- pure schedule logic ----


def test_clamp_minute_snaps_and_bounds():
    assert clamp_minute(22 * 60) == 1320
    assert clamp_minute(67) == 60          # snapped down to the 15-min grid
    assert clamp_minute(-5) == 0
    assert clamp_minute(99999) == 1425     # 23:45, the last grid slot
    assert clamp_minute("nope") == 0


def test_disabled_is_never_active():
    for now in (0, 600, 1400):
        assert is_night_active(now, False, False, 1320, 420) is False
        assert is_night_active(now, False, True, 1320, 420) is False


def test_enabled_without_schedule_is_always_active():
    for now in (0, 600, 1400):
        assert is_night_active(now, True, False, 1320, 420) is True


def test_scheduled_window_wraps_past_midnight():
    # enabled + scheduled, 22:00 -> 07:00
    assert is_night_active(23 * 60, True, True, 1320, 420) is True   # 23:00 inside
    assert is_night_active(3 * 60, True, True, 1320, 420) is True    # 03:00 inside
    assert is_night_active(12 * 60, True, True, 1320, 420) is False  # noon outside
    assert is_night_active(420, True, True, 1320, 420) is False      # 07:00 = end, exclusive


def test_scheduled_window_same_day():
    # enabled + scheduled, 09:00 -> 17:00 (no wrap)
    assert is_night_active(12 * 60, True, True, 540, 1020) is True
    assert is_night_active(8 * 60, True, True, 540, 1020) is False


def test_zero_length_window_never_active():
    assert is_night_active(600, True, True, 600, 600) is False


# ---- store ----


def test_store_defaults(tmp_path):
    s = NightStore(str(tmp_path / "night.json"))
    d = s.get()
    assert d == {"warmth": 40, "enabled": False, "schedule_enabled": False,
                 "start": 1320, "end": 420}


def test_store_set_clamps_and_persists(tmp_path):
    path = str(tmp_path / "night.json")
    NightStore(path).set(warmth=999, enabled=True, schedule_enabled=True, start=67, end=99999)
    d = NightStore(path).get()
    assert d["warmth"] == 100 and d["enabled"] is True and d["schedule_enabled"] is True
    assert d["start"] == 60 and d["end"] == 1425


def test_store_robust_load_bad_json(tmp_path):
    p = tmp_path / "night.json"
    p.write_text("{ not json")
    assert NightStore(str(p)).get()["warmth"] == 40
