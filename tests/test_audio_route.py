from audio.route import classify_route, route_of_sink


def test_classify_speaker():
    assert classify_route("Speaker") == "speaker"
    assert classify_route("alsa_output...analog-stereo") == "speaker"


def test_classify_headphone_and_external():
    assert classify_route("[Out] Headphones") == "headphone"
    assert classify_route("Analog Headset") == "headphone"
    assert classify_route("Bluetooth WH-1000XM4") == "headphone"
    assert classify_route("HDMI / DisplayPort") == "headphone"


def test_classify_empty_defaults_speaker():
    assert classify_route("") == "speaker"
    assert classify_route(None) == "speaker"


_MULTI_SINKS = """Sink #73
\tName: alsa_loopback_device.HiFi__HDMI3__sink
\tActive Port: [Out] HDMI3
Sink #79
\tName: alsa_loopback_device.HiFi__Speaker__sink
\tActive Port: [Out] Speaker
"""


def test_route_of_sink_reads_the_named_sinks_port():
    assert route_of_sink(_MULTI_SINKS, "alsa_loopback_device.HiFi__Speaker__sink") == "speaker"


def test_route_of_sink_defaults_to_speaker_when_sink_absent():
    assert route_of_sink(_MULTI_SINKS, "nonexistent") == "speaker"
    assert route_of_sink(_MULTI_SINKS, None) == "speaker"
