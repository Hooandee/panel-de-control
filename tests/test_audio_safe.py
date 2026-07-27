from audio.safe import (
    band_ceilings,
    clamp_bass,
    clamp_gains,
    safe_limits,
)


def test_generic_fallback_has_ten_band_ceilings():
    lim = safe_limits("unknown_device")
    assert len(lim["bands"]) == 10
    assert all(c > 0 for c in lim["bands"])
    assert isinstance(lim["bass"], int) and lim["bass"] > 0


def test_lows_and_highs_are_tighter_than_the_mids():
    c = band_ceilings("unknown_device")
    peak = max(c)
    assert c[0] < peak   # 32 Hz — cone excursion
    assert c[9] < peak   # 16 kHz — tweeter distortion


def test_clamp_caps_each_bands_positive_boost():
    ceilings = [3, 4, 6, 8, 9, 9, 8, 6, 5, 4]
    out = clamp_gains([12] * 10, ceilings)
    assert out == [3, 4, 6, 8, 9, 9, 8, 6, 5, 4]


def test_clamp_leaves_cuts_and_safe_values_untouched():
    ceilings = [3, 4, 6, 8, 9, 9, 8, 6, 5, 4]
    gains = [-12, -5, 0, 2, 5, -3, 8, 6, -1, 4]
    assert clamp_gains(gains, ceilings) == gains  # every value already within the ceiling


def test_clamp_bass_caps_the_drive():
    assert clamp_bass(100, 60) == 60
    assert clamp_bass(40, 60) == 40
    assert clamp_bass(0, 60) == 0


def test_clamp_gains_tolerates_a_short_ceilings_list():
    out = clamp_gains([12, 12, 12], [3])
    assert out == [3, 12, 12]  # missing ceilings fall back to the full range


def test_known_device_limits_are_ten_bands():
    # Every profiled device must still expose ten band ceilings.
    for key in ("steam_deck", "legion_go", "legion_go_2"):
        assert len(band_ceilings(key)) == 10
