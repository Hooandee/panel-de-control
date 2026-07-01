
from fans import suggest as fan_suggest
from fans.suggest import band, biased_curve, curve_changed, enough_data, suggest_curves

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


# ---------------------------------------------------------------------------
# biased_curve — the silence↔cool dial applied to the learned curves (drives HW;
# mirrors the frontend interpolateCurves so preview == what runs).
# ---------------------------------------------------------------------------

def _curves():
    return {n: [list(p) for p in pts] for n, pts in suggest_curves(band(_good_hist())).items()}


def test_biased_curve_zero_is_balanced():
    c = _curves()
    assert [list(p) for p in biased_curve(c, 0)] == c["balanced"]


def test_biased_curve_negative_is_quieter_positive_is_cooler():
    c = _curves()
    quiet_sum = sum(p for _t, p in biased_curve(c, -100))
    cool_sum = sum(p for _t, p in biased_curve(c, 100))
    bal_sum = sum(p for _t, p in c["balanced"])
    assert quiet_sum <= bal_sum <= cool_sum


def test_biased_curve_clamps_out_of_range_bias():
    c = _curves()
    assert biased_curve(c, 500) == biased_curve(c, 100)
    assert biased_curve(c, -500) == biased_curve(c, -100)


def test_biased_curve_is_sanitized_8_points_monotonic():
    # The result goes through sanitize_curve regardless of bias: 8 points, monotonic
    # temps + pwm, hot-point safety floor — so the driven curve can never be unsafe.
    for bias in (-100, -40, 0, 40, 100):
        cur = biased_curve(_curves(), bias)
        assert len(cur) == 8
        temps = [t for t, _p in cur]
        pwms = [p for _t, p in cur]
        assert temps == sorted(temps)
        assert pwms == sorted(pwms)


def test_min_minutes_is_30():
    assert fan_suggest.MIN_MINUTES == 30


# ---------------------------------------------------------------------------
# curve_changed — anti-churn gate for periodic re-apply (A1)
# ---------------------------------------------------------------------------

def _curve(bump=0):
    base = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]
    return [[t, min(255, p + bump)] for t, p in base]


def test_curve_changed_false_for_identical_curves():
    assert curve_changed(_curve(), _curve()) is False


def test_curve_changed_false_for_tiny_pwm_drift():
    # A drift within tolerance (default 8/255 ≈ 3 %) is not worth a re-write.
    assert curve_changed(_curve(), _curve(bump=5)) is False


def test_curve_changed_true_for_appreciable_shift():
    assert curve_changed(_curve(), _curve(bump=20)) is True


def test_curve_changed_true_when_shape_differs():
    a = _curve()
    b = _curve()
    b[3][1] += 40  # one point moves a lot
    assert curve_changed(a, b) is True


def test_curve_changed_true_when_old_is_none_or_empty():
    # No vigente curve → always "changed" (a first apply must go through).
    assert curve_changed(None, _curve()) is True
    assert curve_changed([], _curve()) is True


def test_curve_changed_respects_custom_tolerance():
    assert curve_changed(_curve(), _curve(bump=5), tol_pwm=2) is True
    assert curve_changed(_curve(), _curve(bump=5), tol_pwm=10) is False
