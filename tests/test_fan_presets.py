from fans.presets import PRESETS, resolve


def test_known_preset_ids():
    assert set(PRESETS) == {"silent", "balanced", "performance"}


def test_resolve_returns_8_safe_points():
    for pid in PRESETS:
        pts = resolve(pid)
        assert len(pts) == 8
        temps = [t for t, _ in pts]
        pwms = [p for _, p in pts]
        assert temps == sorted(temps)  # non-decreasing temps
        assert pwms == sorted(pwms)  # non-decreasing pwm
        assert pwms[-1] >= 76  # safe floor on hottest point
        assert all(0 <= p <= 255 for p in pwms)


def test_resolve_unknown_returns_balanced():
    assert resolve("nope") == resolve("balanced")
