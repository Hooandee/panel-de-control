from audio.route import (
    classify_route,
    route_from_sinks,
    route_of_default_sink,
    route_of_sink,
)

_SPEAKER_SINKS = """Sink #65
\tName: alsa_output.analog-stereo
\t\tanalog-output-headphones: Headphones (not available)
\tActive Port: analog-output-speaker
"""
_HEADPHONE_SINKS = """Sink #65
\tName: alsa_output.analog-stereo
\tActive Port: analog-output-headphones
"""


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


def test_route_from_sinks_reads_active_port():
    assert route_from_sinks(_SPEAKER_SINKS) == "speaker"
    assert route_from_sinks(_HEADPHONE_SINKS) == "headphone"


def test_route_from_sinks_no_active_port_defaults_speaker():
    assert route_from_sinks("Sink #1\n\tName: pdc_eq\n") == "speaker"


def test_route_of_default_sink_uses_reader():
    assert route_of_default_sink(lambda: _HEADPHONE_SINKS) == "headphone"
    assert route_of_default_sink(lambda: _SPEAKER_SINKS) == "speaker"


def test_route_of_default_sink_survives_reader_error():
    def boom():
        raise RuntimeError("no pw")

    assert route_of_default_sink(boom) == "speaker"


_MULTI_SINKS = """Sink #73
\tName: alsa_loopback_device.HiFi__HDMI3__sink
\tActive Port: [Out] HDMI3
Sink #79
\tName: alsa_loopback_device.HiFi__Speaker__sink
\tActive Port: [Out] Speaker
"""


def test_route_of_sink_reads_the_named_sinks_port():
    # HDMI3 is the first Active Port (would read 'headphone'), but we ask for the speaker sink.
    assert route_of_sink(_MULTI_SINKS, "alsa_loopback_device.HiFi__Speaker__sink") == "speaker"


def test_route_of_sink_falls_back_when_sink_absent():
    assert route_of_sink(_MULTI_SINKS, "nonexistent") == route_from_sinks(_MULTI_SINKS)
