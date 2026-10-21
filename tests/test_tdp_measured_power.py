from tdp.measured_power import MeasuredLimitWatch, exceed_threshold_w


def _run(watch, watts, start, seconds, step=2.0):
    verdict = None
    t = start
    while t <= start + seconds:
        verdict = watch.feed(watts, t)
        t += step
    return verdict


def test_waits_for_settle_and_a_full_window():
    watch = MeasuredLimitWatch()
    watch.reset(30, 0.0)

    assert watch.feed(70.0, 2.0).state == "warming"
    assert watch.feed(70.0, 6.0).state == "warming"
    assert _run(watch, 70.0, 8.0, 10.0).state == "exceeded"


def test_apex_like_overshoot_is_exceeded():
    watch = MeasuredLimitWatch()
    watch.reset(30, 0.0)

    verdict = _run(watch, 70.0, 4.0, 14.0)

    assert verdict.state == "exceeded"
    assert verdict.average_w == 70.0
    assert verdict.target_w == 30


def test_measured_ally_limits_stay_within_limit():
    for target, measured in ((6, 6.0), (10, 9.2), (15, 16.5)):
        watch = MeasuredLimitWatch()
        watch.reset(target, 0.0)
        assert _run(watch, measured, 4.0, 14.0).state == "within_limit"


def test_light_load_is_within_limit_not_applied():
    watch = MeasuredLimitWatch()
    watch.reset(25, 0.0)

    assert _run(watch, 5.1, 4.0, 14.0).state == "within_limit"


def test_reset_drops_old_samples_for_a_new_target():
    watch = MeasuredLimitWatch()
    watch.reset(30, 0.0)
    _run(watch, 28.0, 4.0, 14.0)

    watch.reset(10, 20.0)

    assert watch.feed(28.0, 22.0).state == "warming"
    assert _run(watch, 9.0, 24.0, 14.0).state == "within_limit"


def test_missing_power_or_target_never_judges():
    watch = MeasuredLimitWatch()
    assert watch.feed(40.0, 1.0).state == "warming"
    watch.reset(20, 0.0)
    assert watch.feed(None, 10.0).state == "warming"


def test_threshold_has_an_absolute_floor():
    assert exceed_threshold_w(6) == 8.0
    assert exceed_threshold_w(40) == 46.0
