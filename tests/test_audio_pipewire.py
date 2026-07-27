from pathlib import Path

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
        self._default = "alsa_speaker"

    def __call__(self, argv, timeout=8):
        self.calls.append(argv)
        s = " ".join(argv)
        if "get-default-sink" in s:
            return self._default
        if argv[:2] == ["pactl", "set-default-sink"]:
            self._default = argv[2]
            return ""
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


def test_ensure_sink_refuses_to_enable_without_physical_downstream(tmp_path):
    fake = _FakeRunner()
    fake._default = "X EQ"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._downstream_sink = lambda: None

    assert eq.ensure_sink([0] * 10) is False

    assert ["systemctl", "--user", "restart", "filter-chain.service"] not in fake.calls
    assert not any(call[:2] == ["pactl", "set-default-sink"] for call in fake.calls)
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "downstream_missing",
    }


def test_ensure_sink_requires_default_sink_readback(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    def ignore_default_change(argv, timeout=8):
        if argv[:2] == ["pactl", "set-default-sink"]:
            fake.calls.append(argv)
            return ""
        return fake(argv, timeout)

    eq._runner = ignore_default_change

    assert eq.ensure_sink([0] * 10) is False

    assert fake.volume_sets("alsa_speaker") == []
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "default_sink_not_confirmed",
        "downstream": "alsa_speaker",
    }


def test_failed_first_enable_rolls_back_and_retry_preserves_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf = eq._conf_path()
    eq._write_conf = lambda *a, **k: Path(conf).write_text("x") > 0
    failures = {"remaining": 1}
    run = eq._runner

    def fail_first_default_change(argv, timeout=8):
        if argv[:3] == ["pactl", "set-default-sink", "X EQ"]:
            if failures["remaining"]:
                failures["remaining"] -= 1
                fake.calls.append(argv)
                return ""
        return run(argv, timeout)

    eq._runner = fail_first_default_change

    assert eq.ensure_sink([0] * 10) is False
    assert not Path(conf).exists()
    assert eq.ensure_sink([0] * 10) is True

    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]
    assert fake.volume_sets("alsa_speaker") == [
        ["pactl", "set-sink-volume", "alsa_speaker", "100%"],
    ]


def test_disable_after_failed_first_enable_does_not_change_physical_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf = eq._conf_path()
    eq._write_conf = lambda *a, **k: Path(conf).write_text("x") > 0

    def ignore_default_change(argv, timeout=8):
        if argv[:2] == ["pactl", "set-default-sink"]:
            fake.calls.append(argv)
            return ""
        return fake(argv, timeout)

    eq._runner = ignore_default_change
    assert eq.ensure_sink([0] * 10) is False

    eq.teardown()

    assert fake.volume_sets("alsa_speaker") == []
    assert eq.is_active() is False


def test_active_state_drops_when_downstream_disappears(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    assert eq.is_active() is True
    eq._downstream_sink = lambda: None

    assert eq.ensure_sink([0] * 10) is False

    assert eq.is_active() is False
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "downstream_missing",
    }


def test_failed_changed_curve_invalidates_previous_active_state(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    eq._write_conf = lambda *args, **kwargs: False

    assert eq.ensure_sink([3] * 10) is False

    assert eq.is_active() is False
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "config_write_failed",
        "downstream": "alsa_speaker",
    }


def test_disable_after_failed_reapply_restores_owned_eq_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    eq._write_conf = lambda *args, **kwargs: False
    assert eq.ensure_sink([3] * 10) is False

    eq.teardown()

    assert fake.volume_sets("alsa_speaker")[-1] == [
        "pactl",
        "set-sink-volume",
        "alsa_speaker",
        "40%",
    ]
    assert fake._default == "alsa_speaker"


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
