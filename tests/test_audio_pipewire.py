from audio.pipewire import (
    PipeWireEq,
    _relevant_links,
    choose_downstream,
    pick_downstream,
)

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


_DECK_SHORT = (
    "60\talsa_output.HiFi__Speaker__sink\tPipeWire\ts16le 2ch\tIDLE\n"
    "61\talsa_output.HiFi__Headphones__sink\tPipeWire\ts16le 2ch\tRUNNING\n"
)


def test_choose_downstream_prefers_the_active_default():
    assert (
        choose_downstream("alsa_output.HiFi__Headphones__sink", _DECK_SHORT, "X EQ")
        == "alsa_output.HiFi__Headphones__sink"
    )


def test_choose_downstream_falls_back_to_the_running_sink_when_default_is_our_eq():
    # EQ is the default → enumerate, and prefer the RUNNING output (headphones here) so the
    # per-route curve + volume-pin follow the active device, not just the first-listed one.
    assert choose_downstream("X EQ", _DECK_SHORT, "X EQ").endswith("Headphones__sink")


def test_pick_downstream_prefers_running_analog():
    assert pick_downstream(_DECK_SHORT, "X EQ").endswith("Headphones__sink")


def test_choose_downstream_skips_a_digital_default():
    short = (
        "73\talsa_output.HiFi__HDMI1__sink\tPipeWire\t...\tSUSPENDED\n"
        "79\talsa_output.HiFi__Speaker__sink\tPipeWire\t...\tIDLE\n"
    )
    assert choose_downstream("alsa_output.HiFi__HDMI1__sink", short, "X EQ").endswith("Speaker__sink")


class _FakeRunner:
    def __init__(self, downstream_vol="40%"):
        self.calls = []
        self._vol = downstream_vol

    def __call__(self, argv, timeout=8):
        self.calls.append(argv)
        s = " ".join(argv)
        if "get-default-sink" in s:
            return "alsa_speaker"
        if "list" in s and "sinks" in s:
            return "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        if "get-sink-volume" in s:
            return f"Volume: front-left: 26214 / {self._vol} / ..."
        return ""

    def volume_sets(self, sink):
        return [c for c in self.calls
                if c[:2] == ["pactl", "set-sink-volume"] and c[2] == sink]


def _make_eq(tmp_path, fake, conf_exists):
    eq = PipeWireEq(runner=fake, name="X")
    eq._session = (1000, "/run/user/1000", "deck")
    conf = tmp_path / "pdc-eq.conf"
    if conf_exists:
        conf.write_text("x")
    eq._conf_path = lambda: str(conf)
    eq.is_supported = lambda: True
    eq._write_conf = lambda *a, **k: True
    return eq


def test_ensure_sink_first_enable_carries_downstream_volume(tmp_path):
    # Genuine first-ever enable (no persisted conf): carry the downstream's real level
    # onto our sink so enabling the EQ doesn't jump loudness to unity.
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == [["pactl", "set-sink-volume", "X EQ", "40%"]]
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


def test_ensure_sink_boot_reassert_preserves_user_volume(tmp_path):
    # A persisted conf already exists → the EQ sink comes back with the user's level
    # (WirePlumber restores it by node.name). A boot/reload re-assert must NOT copy the
    # always-unity downstream onto it, or the user's volume is wiped to 100% every boot.
    fake = _FakeRunner(downstream_vol="100%")
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == []
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


_PW_LINK = """effect_output.pdc_eq:output_FL
  |-> alsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo:playback_FL
alsa_output.pci-0000_c2_00.6.analog-stereo:playback_FL
  |<- alsa_loopback_stream.alsa_output.pci-0000_c2_00.6.analog-stereo:output_FL
some_unrelated_node:port
  |-> another_unrelated:in
"""


def test_relevant_links_keeps_eq_and_hardware_drops_noise():
    out = _relevant_links(_PW_LINK)
    assert "effect_output.pdc_eq" in out          # our node
    assert "alsa_output.pci-0000_c2_00.6" in out   # hardware output
    assert "loopback" in out                        # the virtual hop it routes through
    assert "some_unrelated_node" not in out         # noise dropped
    # the indented continuation of a kept node is preserved
    assert "|-> alsa_loopback_device" in out


def test_relevant_links_empty_and_capped():
    assert _relevant_links("") == ""
    assert _relevant_links(None) == ""
    big = "\n".join("alsa_output.sink%d:port" % i for i in range(5000))
    assert len(_relevant_links(big, cap=500)) == 500
