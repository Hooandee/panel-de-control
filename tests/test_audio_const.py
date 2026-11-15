from audio.const import (
    GAIN_MAX,
    GAIN_MIN,
    clamp_gain,
    compute_preamp,
)


def test_clamp_gain():
    assert clamp_gain(99) == GAIN_MAX
    assert clamp_gain(-99) == GAIN_MIN
    assert clamp_gain(3.5) == 3.5
    assert clamp_gain("bad") == 0.0


def test_preamp_is_negative_headroom():
    assert compute_preamp([0] * 10) == 0.0
    assert compute_preamp([6, 0, 3, 0, 0, 0, 0, 0, 0, 0]) == -6.0
    assert compute_preamp([-3, -6, 0, 0, 0, 0, 0, 0, 0, 0]) == 0.0
