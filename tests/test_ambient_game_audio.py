import json

from ambient.adapters.game_audio import GameAudio, game_streams


def _stream(index, binary=None, node="x", percent="100%"):
    props = {"node.name": node}
    if binary:
        props["application.process.binary"] = binary
    return {"index": index, "properties": props, "volume": {"front-left": {"value_percent": percent}, "front-right": {"value_percent": percent}}}


def test_only_game_streams_are_picked():
    listing = [_stream(1, "steamwebhelper", "Chromium"), _stream(2, node="effect_output.pdc_eq"), _stream(3, "wine64-preloader", "game", "80%")]
    assert game_streams(listing) == [(3, 80)]


def test_sets_only_streams_that_differ():
    calls = []
    listing = json.dumps([_stream(3, "game", percent="40%"), _stream(4, "other", percent="100%")])

    def runner(argv):
        calls.append(argv)
        return listing if argv[:3] == ["pactl", "-f", "json"] else ""

    assert GameAudio(runner).set_level(40) == {"supported": True, "streams": 2}
    assert calls[1:] == [["pactl", "set-sink-input-volume", "4", "40%"]]


def test_reports_unsupported_without_pactl_json():
    assert GameAudio(lambda argv: None).set_level(50) == {"supported": False, "streams": 0}
    assert GameAudio(lambda argv: "Unknown option -f").set_level(50) == {"supported": False, "streams": 0}
