from audio.route import classify_route, route_of_default_sink


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


def test_route_of_default_sink_uses_reader():
    assert route_of_default_sink(lambda: "Analog Headphones") == "headphone"
    assert route_of_default_sink(lambda: "Speaker") == "speaker"


def test_route_of_default_sink_survives_reader_error():
    def boom():
        raise RuntimeError("no pw")

    assert route_of_default_sink(boom) == "speaker"
