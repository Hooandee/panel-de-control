from audio.pipewire import sink_volume_arg


def test_preamp_zero_is_full_volume():
    assert sink_volume_arg(0.0) == "100%"


def test_negative_preamp_attenuates():
    # -6 dB ≈ half amplitude, -12 dB ≈ quarter.
    assert sink_volume_arg(-6.0) == "50%"
    assert sink_volume_arg(-12.0) == "25%"


def test_positive_preamp_never_exceeds_full():
    assert sink_volume_arg(3.0) == "100%"
