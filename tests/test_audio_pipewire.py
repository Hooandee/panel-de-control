from audio.pipewire import pick_downstream

_SINKS = (
    "45\teffect_input.pdc_eq\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n"
    "61\talsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo\tPipeWire\t...\tIDLE\n"
)


def test_pick_downstream_skips_our_sink():
    assert pick_downstream(_SINKS, "effect_input.pdc_eq") == (
        "alsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo"
    )


def test_pick_downstream_none_when_only_ours():
    only_ours = "45\teffect_input.pdc_eq\tPipeWire\ts16le 2ch\tRUNNING\n"
    assert pick_downstream(only_ours, "effect_input.pdc_eq") is None


def test_pick_downstream_empty():
    assert pick_downstream("", "effect_input.pdc_eq") is None
    assert pick_downstream(None, "effect_input.pdc_eq") is None


_MULTI_SINKS = (
    "45\teffect_input.pdc_eq\tPipeWire\ts16le 2ch\tRUNNING\n"
    "73\talsa_loopback_device.HiFi__HDMI3__sink\tPipeWire\t...\tSUSPENDED\n"
    "79\talsa_loopback_device.HiFi__Speaker__sink\tPipeWire\t...\tIDLE\n"
)


def test_pick_downstream_prefers_analog_over_hdmi():
    assert pick_downstream(_MULTI_SINKS, "effect_input.pdc_eq").endswith("Speaker__sink")


def test_pick_downstream_falls_back_to_first_when_all_digital():
    only_hdmi = "73\talsa_loopback_device.HiFi__HDMI3__sink\tPipeWire\t...\tSUSPENDED\n"
    assert pick_downstream(only_hdmi, "x").endswith("HDMI3__sink")
