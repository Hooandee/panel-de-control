
from fans.suggest import band, enough_data, suggest_curves

_SAFE_FLOOR = 76  # must match fans.control._SAFE_MAX_TEMP_FLOOR


def _hist(pairs):
    """Build a temp histogram {bin: seconds} from (temp_bin, seconds) pairs."""
    return {int(t): float(s) for t, s in pairs}


# A realistic "this game sits 58–82 °C" distribution with >30 min of dwell.
def _good_hist():
    return _hist([
        (54, 120), (58, 300), (62, 600), (66, 900),
        (70, 800), (74, 500), (78, 300), (82, 120),
    ])


# ---------------------------------------------------------------------------
# enough_data
# ---------------------------------------------------------------------------

def test_enough_data_empty_is_no_data(tmp_path):
    ok, reason = enough_data({})
    assert ok is False
    assert reason == "no_data"


def test_enough_data_below_30min_is_too_few():
    ok, reason = enough_data(_hist([(60, 300), (66, 400)]))  # 700 s < 1800
    assert ok is False
    assert reason == "too_few"


def test_enough_data_flat_band_is_flat():
    # Plenty of time but all mass in two adjacent bins → spread < 8 °C
    ok, reason = enough_data(_hist([(70, 1200), (72, 1200)]))
    assert ok is False
    assert reason == "flat"


def test_enough_data_good_distribution_is_ok():
    ok, reason = enough_data(_good_hist())
    assert ok is True
    assert reason == "ok"


# ---------------------------------------------------------------------------
# band — percentiles ordered and within observed range
# ---------------------------------------------------------------------------

def test_band_percentiles_ordered_and_in_range():
    b = band(_good_hist())
    assert b["floor"] <= b["typical"] <= b["high"] <= b["peak"]
    assert 54 <= b["floor"]
    assert b["peak"] <= 82


# ---------------------------------------------------------------------------
# suggest_curves
# ---------------------------------------------------------------------------

def test_suggest_curves_returns_three_named_8point_curves():
    curves = suggest_curves(band(_good_hist()))
    assert set(curves) == {"quiet", "balanced", "cool"}
    for pts in curves.values():
        assert len(pts) == 8


def test_suggest_curves_monotonic_and_safe_floor():
    curves = suggest_curves(band(_good_hist()))
    for pts in curves.values():
        temps = [t for t, _ in pts]
        pwms = [p for _, p in pts]
        assert temps == sorted(temps)
        assert pwms == sorted(pwms)
        assert pwms[-1] >= _SAFE_FLOOR  # never idle when hot


def test_cool_is_louder_than_balanced_than_quiet():
    curves = suggest_curves(band(_good_hist()))

    def duty_at(pts, temp):
        # pwm of the anchor nearest >= temp (curves share temp anchors)
        for t, p in pts:
            if t >= temp:
                return p
        return pts[-1][1]

    q = duty_at(curves["quiet"], 70)
    b = duty_at(curves["balanced"], 70)
    c = duty_at(curves["cool"], 70)
    assert c >= b >= q
    assert c > q  # the dial must actually do something
