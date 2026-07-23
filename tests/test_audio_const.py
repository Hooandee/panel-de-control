from audio.const import (
    BAND_FREQS,
    GAIN_MAX,
    GAIN_MIN,
    ROUTES,
    WIDTH_NEUTRAL,
    clamp_gain,
    clamp_pct,
    compute_preamp,
    crossfeed_gain,
    width_factor,
)


def test_ten_bands():
    assert BAND_FREQS == [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def test_routes():
    assert ROUTES == ["speaker", "headphone"]


def test_clamp_gain():
    assert clamp_gain(99) == GAIN_MAX
    assert clamp_gain(-99) == GAIN_MIN
    assert clamp_gain(3.5) == 3.5
    assert clamp_gain("bad") == 0.0


def test_preamp_is_negative_headroom():
    assert compute_preamp([0] * 10) == 0.0
    assert compute_preamp([6, 0, 3, 0, 0, 0, 0, 0, 0, 0]) == -6.0
    assert compute_preamp([-3, -6, 0, 0, 0, 0, 0, 0, 0, 0]) == 0.0


def test_clamp_pct():
    assert clamp_pct(150) == 100
    assert clamp_pct(-5) == 0
    assert clamp_pct(37) == 37
    assert clamp_pct("bad") == 0


def test_width_factor_neutral_is_one():
    assert width_factor(WIDTH_NEUTRAL) == 1.0
    assert width_factor(0) == 0.0        # mono
    assert width_factor(100) == 2.0      # max wide
    assert width_factor(25) == 0.5


def test_crossfeed_gain():
    assert crossfeed_gain(0) == 0.0      # off
    assert crossfeed_gain(100) == 0.6    # full
    assert crossfeed_gain(50) == 0.3
