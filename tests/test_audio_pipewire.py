import json
import os
import stat
from pathlib import Path

import audio.pipewire as pipewire

from audio.pipewire import (
    PipeWireEq,
    _MAX_ENTRY_BYTES,
    _configured_default_sink,
    _linked_downstream,
    _link_reaches,
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
    assert choose_downstream("X EQ", _DECK_SHORT, "X EQ").endswith("Headphones__sink")


def test_pick_downstream_prefers_running_analog():
    assert pick_downstream(_DECK_SHORT, "X EQ").endswith("Headphones__sink")


def test_choose_downstream_honors_a_selected_digital_default():
    short = (
        "73\talsa_output.HiFi__HDMI1__sink\tPipeWire\t...\tSUSPENDED\n"
        "79\talsa_output.HiFi__Speaker__sink\tPipeWire\t...\tIDLE\n"
    )
    assert choose_downstream("alsa_output.HiFi__HDMI1__sink", short, "X EQ").endswith("HDMI1__sink")


def test_pick_downstream_prefers_running_hdmi_over_idle_speaker():
    short = (
        "73\talsa_output.HiFi__HDMI1__sink\tPipeWire\t...\tRUNNING\n"
        "79\talsa_output.HiFi__Speaker__sink\tPipeWire\t...\tIDLE\n"
    )

    assert pick_downstream(short, "X EQ").endswith("HDMI1__sink")


def test_choose_downstream_ignores_a_stale_missing_default():
    assert (
        choose_downstream("alsa_output.missing", _DECK_SHORT, "X EQ")
        == "alsa_output.HiFi__Headphones__sink"
    )


def test_choose_downstream_retains_confirmed_idle_target_while_eq_is_default():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream("X EQ", short, "X EQ", preferred="bluez_output.headset")
        == "bluez_output.headset"
    )


def test_choose_downstream_prefers_the_current_link_over_the_previous_target():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream(
            "X EQ",
            short,
            "X EQ",
            preferred="alsa_speaker",
            linked="alsa_output.hdmi",
        )
        == "alsa_output.hdmi"
    )


def test_choose_downstream_prefers_a_new_configured_default_while_eq_is_default():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream(
            "X EQ",
            short,
            "X EQ",
            preferred="alsa_speaker",
            linked="alsa_speaker",
            configured="alsa_output.hdmi",
            configured_changed=True,
        )
        == "alsa_output.hdmi"
    )


def test_choose_downstream_uses_configured_default_when_recovering_an_existing_eq():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream(
            "X EQ",
            short,
            "X EQ",
            linked="alsa_speaker",
            configured="alsa_output.hdmi",
        )
        == "alsa_output.hdmi"
    )


def test_choose_downstream_honors_a_manual_link_move_when_configured_default_is_unchanged():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream(
            "X EQ",
            short,
            "X EQ",
            preferred="alsa_speaker",
            linked="bluez_output.headset",
            configured="alsa_speaker",
        )
        == "bluez_output.headset"
    )


def test_choose_downstream_keeps_confirmed_link_when_configured_default_is_stale():
    short = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert (
        choose_downstream(
            "X EQ",
            short,
            "X EQ",
            preferred="bluez_output.headset",
            linked="bluez_output.headset",
            configured="alsa_speaker",
            configured_changed=False,
        )
        == "bluez_output.headset"
    )


def test_configured_default_sink_parses_wireplumber_metadata():
    metadata = """Found \"default\" metadata 41
update: id:0 key:'default.configured.audio.sink' value:'{ \"name\": \"alsa_output.hdmi\" }' type:'Spa:String:JSON'
update: id:0 key:'default.audio.sink' value:'{\"name\":\"X EQ\"}' type:'Spa:String:JSON'
"""

    assert _configured_default_sink(metadata) == "alsa_output.hdmi"
    assert _configured_default_sink("") is None


def test_link_readback_requires_exact_node_names():
    links = (
        "effect_output.pdc_eq:output_FL\n"
        "  |-> alsa_output.hdmi-stereo-extra1:playback_FL\n"
    )

    assert not _link_reaches(
        links,
        "effect_output.pdc_eq",
        "alsa_output.hdmi-stereo",
    )
    assert _linked_downstream(
        links,
        "effect_output.pdc_eq",
        ["alsa_output.hdmi-stereo", "alsa_output.hdmi-stereo-extra1"],
    ) == "alsa_output.hdmi-stereo-extra1"

class _FakeRunner:
    def __init__(self, downstream_vol="40%"):
        self.calls = []
        if isinstance(downstream_vol, dict):
            self._volumes = dict(downstream_vol)
            self._vol = next(iter(self._volumes.values()), "40%")
        else:
            self._volumes = {}
            self._vol = downstream_vol
        self._volume_channels = {}
        self._mutes = {}
        self._default = "alsa_speaker"
        self._link_target = "alsa_speaker"
        self._configured_target = None
        self._configured_default = None
        self._sinks = "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        self._service_generation = 1
        self._conf_path = None
        self._keep_eq_on_restart = False

    def __call__(self, argv, timeout=8):
        self.calls.append(argv)
        s = " ".join(argv)
        if "get-default-sink" in s:
            return self._default
        if argv[:2] == ["pactl", "set-default-sink"]:
            self._default = argv[2]
            self._configured_default = argv[2]
            return ""
        if argv[:2] == ["pactl", "set-sink-volume"]:
            values = [value for value in argv[3:] if value.endswith("%")]
            if values:
                self._volumes[argv[2]] = values[0]
                self._volume_channels[argv[2]] = tuple(values)
            return ""
        if argv[:2] == ["pactl", "set-sink-mute"]:
            self._mutes[argv[2]] = argv[3] in ("1", "yes", "true")
            return ""
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            self._service_generation += 1
            if self._configured_target:
                self._link_target = self._configured_target
            elif not self._default.endswith(" EQ"):
                self._link_target = self._default
            if (
                self._conf_path
                and not Path(self._conf_path).exists()
                and not self._keep_eq_on_restart
            ):
                self._sinks = "\n".join(
                    line for line in self._sinks.splitlines() if "\tX EQ\t" not in line
                )
                if self._sinks:
                    self._sinks += "\n"
            return ""
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            return "active"
        if argv == [
            "systemctl",
            "--user",
            "show",
            "filter-chain.service",
            "--property=InvocationID",
            "--property=MainPID",
            "--value",
        ]:
            return f"inv-{self._service_generation}\n{1000 + self._service_generation}"
        if argv == ["pw-link", "-l"]:
            return (
                "effect_output.pdc_eq:output_FL\n"
                f"  |-> {self._link_target}:playback_FL\n"
            )
        if argv == ["pw-metadata", "-n", "default"]:
            if self._configured_default:
                return (
                    "update: id:0 key:'default.configured.audio.sink' "
                    f"value:'{{ \"name\": \"{self._configured_default}\" }}' "
                    "type:'Spa:String:JSON'"
                )
            return ""
        if argv[:5] == [
            "pw-metadata",
            "-n",
            "default",
            "0",
            "default.audio.sink",
        ]:
            self._default = json.loads(argv[5])["name"]
            return ""
        if "list" in s and "sinks" in s:
            return self._sinks
        if "get-sink-volume" in s:
            sink = argv[-1]
            values = self._volume_channels.get(sink)
            if values:
                return "Volume: " + " ".join(
                    f"channel-{index}: 26214 / {value} / ..."
                    for index, value in enumerate(values)
                )
            volume = self._volumes.get(sink, self._vol)
            return f"Volume: front-left: 26214 / {volume} / ..."
        if "get-sink-mute" in s:
            return "Mute: yes" if self._mutes.get(argv[-1], False) else "Mute: no"
        return ""

    def volume_sets(self, sink):
        return [c for c in self.calls
                if c[:2] == ["pactl", "set-sink-volume"] and c[2] == sink]


def _make_eq(tmp_path, fake, conf_exists):
    eq = PipeWireEq(runner=fake, name="X")
    eq._session = (os.getuid(), f"/run/user/{os.getuid()}", "deck")
    conf = tmp_path / "pdc-eq.conf"
    if conf_exists:
        conf.write_text("x")
    eq._conf_path = lambda: str(conf)
    fake._conf_path = str(conf)
    eq.is_supported = lambda: True
    eq._sleep = lambda _delay: None
    def write_conf(*args, **kwargs):
        fake._configured_target = kwargs.get("downstream") or args[-1]
        conf.write_text("x")
        return True

    eq._write_conf = write_conf
    return eq


def test_ensure_sink_first_enable_carries_downstream_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "100%"],
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


def test_first_enable_stages_unity_before_switching_the_default(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None

    assert eq.ensure_sink([0] * 10) is True

    stage = fake.calls.index(["pactl", "set-sink-volume", "X EQ", "100%"])
    switch = fake.calls.index(["pactl", "set-default-sink", "X EQ"])
    commit = fake.calls.index(["pactl", "set-sink-volume", "X EQ", "40%"])
    pin = fake.calls.index(["pactl", "set-sink-volume", "alsa_speaker", "100%"])
    assert stage < switch < commit < pin


def test_first_enable_without_volume_readback_stays_on_the_physical_sink(tmp_path):
    fake = _FakeRunner(downstream_vol="")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert fake.volume_sets("alsa_speaker") == []
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "downstream_volume_missing",
        "downstream": "alsa_speaker",
    }


def test_first_enable_requires_unity_stage_readback(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def ignore_unity_stage(argv, timeout=8):
        if argv == ["pactl", "set-sink-volume", "X EQ", "100%"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_unity_stage

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert fake.volume_sets("alsa_speaker") == [
        ["pactl", "set-sink-volume", "alsa_speaker", "40%"],
    ]
    assert eq.apply_diagnostics()["reason"] == "eq_volume_stage_not_confirmed"


def test_first_enable_requires_eq_volume_commit_readback(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def ignore_eq_commit(argv, timeout=8):
        if argv == ["pactl", "set-sink-volume", "X EQ", "40%"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_eq_commit

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert fake._volumes["alsa_speaker"] == "40%"
    assert eq.apply_diagnostics()["reason"] == "eq_volume_commit_not_confirmed"


def test_first_enable_requires_physical_pin_readback(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def ignore_physical_pin(argv, timeout=8):
        if argv == ["pactl", "set-sink-volume", "alsa_speaker", "100%"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_physical_pin

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert fake._volumes["alsa_speaker"] == "40%"
    assert eq.apply_diagnostics()["reason"] == "downstream_volume_pin_not_confirmed"


def test_default_reversion_after_physical_pin_rolls_back_without_publishing(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    run = eq._runner

    def revert_after_pin(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["pactl", "set-sink-volume", "alsa_speaker", "100%"]:
            fake._default = "alsa_speaker"
            fake._configured_default = "alsa_speaker"
        return result

    eq._runner = revert_after_pin

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert fake._volumes["alsa_speaker"] == "40%"
    assert eq.is_active() is False
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "post_pin_route_not_confirmed",
        "downstream": "alsa_speaker",
        "current": "alsa_speaker",
        "rollback_confirmed": True,
    }


def test_mute_ownership_moves_to_eq_and_back_to_the_physical_sink(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    fake._mutes["alsa_speaker"] = True
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    assert eq.ensure_sink([0] * 10) is True
    assert fake._mutes["X EQ"] is True
    assert fake._mutes["alsa_speaker"] is False

    fake._mutes["X EQ"] = False
    assert eq.teardown() is True
    assert fake._mutes["alsa_speaker"] is False


def test_mute_selected_while_eq_is_active_survives_teardown(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._mutes["X EQ"] = True

    assert eq.teardown() is True
    assert fake._mutes["alsa_speaker"] is True


def test_volume_selected_while_eq_is_active_survives_teardown(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake(["pactl", "set-sink-volume", "X EQ", "55%"])

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "55%"


def test_hotplug_during_default_confirmation_aborts_before_volume_commit(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    set_default = eq._set_default_confirmed

    def confirm_then_hotplug(sink, expected_downstream=None):
        confirmed = set_default(sink, expected_downstream)
        if sink == "X EQ":
            fake._default = "X EQ"
            fake._link_target = "bluez_output.headset"
            fake._sinks = (
                "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
                "3\tX EQ\tPipeWire\t...\tRUNNING\n"
            )
        return confirmed

    eq._set_default_confirmed = confirm_then_hotplug

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "bluez_output.headset"
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] not in fake.calls
    assert ["pactl", "set-sink-volume", "bluez_output.headset", "100%"] not in fake.calls
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "downstream_changed_during_default",
            "downstream": "alsa_speaker",
            "current": "bluez_output.headset",
            "bypass_confirmed": True,
            "rollback_confirmed": False,
        }
    assert eq._route_state()["pending_restores"][0]["sink"] == "alsa_speaker"


def test_pactl_handoff_restores_physical_configured_default_on_teardown(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    fake._configured_default = "alsa_speaker"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner
    transient = {"pending": False}

    def model_configured_default(argv, timeout=8):
        result = run(argv, timeout)
        if argv[:5] == [
            "pw-metadata",
            "-n",
            "default",
            "0",
            "default.audio.sink",
        ]:
            transient["pending"] = True
        elif argv == ["pactl", "get-default-sink"] and transient["pending"]:
            transient["pending"] = False
            fake._default = "alsa_speaker"
        elif argv[:2] == ["pactl", "set-default-sink"]:
            fake._configured_default = argv[2]
        return result

    eq._runner = model_configured_default

    assert eq.ensure_sink([0] * 10) is True
    assert fake._configured_default == "X EQ"
    assert eq.teardown() is True
    assert fake._default == "alsa_speaker"
    assert fake._configured_default == "alsa_speaker"


def test_pactl_fallback_handoff_restores_the_latest_physical_intent(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    fake._configured_default = "alsa_speaker"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner
    transient = {"pending": False}

    def model_configured_default(argv, timeout=8):
        result = run(argv, timeout)
        if argv[:5] == [
            "pw-metadata",
            "-n",
            "default",
            "0",
            "default.audio.sink",
        ]:
            transient["pending"] = True
        elif argv == ["pactl", "get-default-sink"] and transient["pending"]:
            transient["pending"] = False
            fake._default = "alsa_speaker"
        elif argv[:2] == ["pactl", "set-default-sink"]:
            fake._configured_default = argv[2]
        return result

    eq._runner = model_configured_default
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    assert eq.ensure_sink([0] * 10) is True
    assert eq._active_downstream == "bluez_output.headset"
    assert fake._configured_default == "X EQ"

    assert eq.teardown() is True
    assert fake._default == "bluez_output.headset"
    assert fake._configured_default == "bluez_output.headset"


def test_empty_default_readback_aborts_before_physical_volume_pin(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner
    probing = {"active": False}

    def lose_default_readback(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["pactl", "set-default-sink", "X EQ"]:
            probing["active"] = True
        if argv == ["pactl", "get-default-sink"] and probing["active"]:
            return ""
        return result

    eq._runner = lose_default_readback

    assert eq.ensure_sink([0] * 10) is False
    assert fake.calls.count(["pactl", "set-default-sink", "X EQ"]) == 1
    assert fake.volume_sets("alsa_speaker") == []


def test_route_change_during_default_confirmation_is_not_overridden(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    fake._configured_default = "alsa_speaker"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner
    probing = {"reads": 0}

    def select_headset_during_probe(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["pactl", "get-default-sink"] and fake._default == "X EQ":
            probing["reads"] += 1
            if probing["reads"] == 2:
                fake._default = "bluez_output.headset"
                fake._configured_default = "bluez_output.headset"
                fake._link_target = "bluez_output.headset"
                fake._sinks = (
                    "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
                    "3\tX EQ\tPipeWire\t...\tRUNNING\n"
                )
        return result

    eq._runner = select_headset_during_probe

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "bluez_output.headset"
    assert fake.calls.count(["pactl", "set-default-sink", "X EQ"]) == 1
    assert fake.volume_sets("alsa_speaker") == []
    assert fake.volume_sets("bluez_output.headset") == []


def test_first_enable_rolls_back_when_all_eq_default_writes_are_transient(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    run = eq._runner
    transient = {"pending": False}

    def revert_eq_default(argv, timeout=8):
        result = run(argv, timeout)
        if (
            argv[:5]
            == ["pw-metadata", "-n", "default", "0", "default.audio.sink"]
            or argv == ["pactl", "set-default-sink", "X EQ"]
        ):
            transient["pending"] = True
        elif argv == ["pactl", "get-default-sink"] and transient["pending"]:
            transient["pending"] = False
            fake._default = "alsa_speaker"
        return result

    eq._runner = revert_eq_default

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] not in fake.calls
    assert Path(eq._conf_path()).exists()
    assert eq._route_state()["phase"] == "prepared"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "default_sink_not_confirmed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
        "current": "alsa_speaker",
    }


def test_first_enable_creates_a_missing_pipewire_config_directory(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf = tmp_path / "missing" / "filter-chain.conf.d" / "pdc-eq.conf"
    eq._conf_path = lambda: str(conf)
    fake._conf_path = str(conf)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    assert eq.ensure_sink([0] * 10) is True
    assert conf.exists()
    assert json.loads(Path(f"{conf}.first-enable-pending").read_text()) == {
        "sink": "alsa_speaker",
        "volume": "40%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": False,
        "pending_restores": [],
    }


def test_volume_marker_refuses_to_follow_a_symlink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    marker = Path(eq._pending_path())
    marker.symlink_to(victim)
    eq._first_enable_downstream = "alsa_speaker"
    eq._first_enable_volume = "40%"
    eq._first_enable_volumes = ("40%",)
    eq._first_enable_mute = False

    assert eq._persist_first_enable_pending() is False
    assert victim.read_text() == "unchanged"
    assert marker.is_symlink()


def test_config_refuses_to_replace_a_symlink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    conf = Path(eq._conf_path())
    conf.symlink_to(victim)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    assert eq._write_conf([0] * 10, 0, False, "alsa_speaker") is False
    assert victim.read_text() == "unchanged"
    assert conf.is_symlink()


def test_config_ignores_the_old_deterministic_pending_symlink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    legacy_pending = Path(f"{eq._conf_path()}.pending")
    legacy_pending.symlink_to(victim)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    assert eq._write_conf([0] * 10, 0, False, "alsa_speaker") is True
    assert victim.read_text() == "unchanged"
    assert legacy_pending.is_symlink()


def test_config_refuses_to_traverse_a_symlinked_parent(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    conf = linked_parent / "pdc-eq.conf"
    eq._conf_path = lambda: str(conf)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    assert eq._write_conf([0] * 10, 0, False, "alsa_speaker") is False
    assert not (real_parent / "pdc-eq.conf").exists()


def test_secure_remove_does_not_confirm_through_a_symlinked_parent(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    real_parent = tmp_path / "real-remove"
    real_parent.mkdir()
    entry = real_parent / "marker"
    entry.write_text("keep")
    linked_parent = tmp_path / "linked-remove"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    assert eq._remove_entry(str(linked_parent / "marker")) is False
    assert entry.read_text() == "keep"


def test_missing_parent_confirms_pending_marker_absence(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._conf_path = lambda: str(tmp_path / "missing" / "pdc-eq.conf")

    assert eq._clear_first_enable_pending() is True


def test_secure_entry_io_rejects_oversized_files(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"x" * (_MAX_ENTRY_BYTES + 1))

    assert eq._read_entry(str(oversized)) is None
    assert eq._write_entry(str(tmp_path / "new"), "x" * (_MAX_ENTRY_BYTES + 1)) is False
    assert not (tmp_path / "new").exists()


def test_secure_read_rejects_a_fifo_without_blocking(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)

    assert eq._read_entry(str(fifo)) is None


def test_config_and_volume_marker_are_private_to_the_session_user(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._first_enable_downstream = "alsa_speaker"
    eq._first_enable_volume = "40%"
    eq._first_enable_volumes = ("40%",)
    eq._first_enable_mute = False

    assert eq._persist_first_enable_pending() is True
    assert stat.S_IMODE(os.stat(eq._pending_path()).st_mode) == 0o600

    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)
    assert eq._write_conf([0] * 10, 0, False, "alsa_speaker") is True
    assert stat.S_IMODE(os.stat(eq._conf_path()).st_mode) == 0o600


def test_secure_write_refuses_to_publish_with_the_wrong_owner(tmp_path, monkeypatch):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    def reject_chown(_fd, _uid, _gid):
        raise OSError("ownership unsupported")

    class WrongOwner:
        st_uid = os.getuid() + 1

    monkeypatch.setattr(os, "fchown", reject_chown)
    monkeypatch.setattr(os, "fstat", lambda _fd: WrongOwner())

    target = tmp_path / "wrong-owner"
    assert eq._write_entry(str(target), "data") is False
    assert not target.exists()


def test_trusted_home_alias_is_resolved_before_secure_directory_walk(
    tmp_path, monkeypatch
):
    real_home = tmp_path / "var-home" / "deck"
    real_home.mkdir(parents=True)
    home_alias = tmp_path / "home-deck"
    home_alias.symlink_to(real_home, target_is_directory=True)

    class Account:
        pw_dir = str(home_alias)
        pw_uid = os.getuid()
        pw_gid = os.getgid()

    monkeypatch.setattr(pipewire.pwd, "getpwuid", lambda _uid: Account())
    fake = _FakeRunner()
    eq = PipeWireEq(runner=fake, name="X")
    eq._session = (os.getuid(), "/run/user/test", "deck")
    eq.is_supported = lambda: True
    fake._conf_path = eq._conf_path()

    assert eq._conf_path().startswith(str(real_home))
    assert eq.ensure_sink([0] * 10) is True
    assert Path(eq._conf_path()).exists()


def test_boot_activation_from_physical_default_preserves_user_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="100%")
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "100%"],
    ]
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


def test_reassert_with_eq_already_default_never_stages_audible_volume(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "X EQ": "40%",
    })
    fake._default = "X EQ"
    fake._configured_default = "alsa_speaker"
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._sleep = lambda _delay: None

    assert eq.ensure_sink([0] * 10) is True
    assert ["pactl", "set-sink-volume", "X EQ", "100%"] not in fake.calls
    assert fake._volumes["X EQ"] == "40%"


def test_same_curve_restarts_filter_chain_when_output_changes(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    initial_restarts = fake.calls.count(["systemctl", "--user", "restart", "filter-chain.service"])

    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert eq.ensure_sink([0] * 10) is True
    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == initial_restarts + 1


def test_configured_output_change_survives_probe_then_apply(tmp_path):
    fake = _FakeRunner()
    fake._configured_default = "alsa_speaker"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    assert eq._downstream_sink() == "alsa_speaker"

    fake._configured_default = "alsa_output.hdmi"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert eq._downstream_sink() == "alsa_output.hdmi"
    assert eq._downstream_sink() == "alsa_output.hdmi"
    assert eq.ensure_sink([0] * 10) is True
    assert eq._active_downstream == "alsa_output.hdmi"


def test_configured_output_change_makes_active_readback_fail_before_handoff(tmp_path):
    fake = _FakeRunner()
    fake._configured_default = "alsa_speaker"
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    assert eq.is_active() is True

    fake._configured_default = "alsa_output.hdmi"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert eq.is_active() is False
    assert eq._requested_downstream == "alsa_output.hdmi"


def test_route_change_restores_the_previous_output_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._vol = "65%"
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert eq.ensure_sink([0] * 10) is True

    assert fake.volume_sets("alsa_speaker")[-1] == [
        "pactl",
        "set-sink-volume",
        "alsa_speaker",
        "40%",
    ]


def test_teardown_restores_the_latest_selected_output(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    assert eq.ensure_sink([0] * 10) is True

    eq.teardown()

    assert fake._default == "bluez_output.headset"


def test_teardown_preserves_a_new_external_default_before_watcher_handoff(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    checkpoint = len(fake.calls)

    eq.teardown()

    assert fake._default == "bluez_output.headset"
    assert not any(call[:2] == ["pactl", "set-default-sink"] for call in fake.calls[checkpoint:])


def test_teardown_falls_back_to_a_live_sink_after_hot_unplug(tmp_path):
    fake = _FakeRunner()
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10, balance=30) is True

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )

    assert eq.teardown() is False

    assert fake._default == "alsa_speaker"
    assert eq._route_state()["pending_restores"][0]["sink"] == (
        "bluez_output.headset"
    )

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
    )
    eq._monotonic = lambda: 100.0

    assert eq.teardown() is True
    assert eq.apply_diagnostics()["ok"] is True


def test_route_handoff_retargets_while_eq_remains_default(tmp_path):
    fake = _FakeRunner()
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    checkpoint = len(fake.calls)

    assert eq.ensure_sink([0] * 10) is True

    handoff = fake.calls[checkpoint:]
    restart = handoff.index(["systemctl", "--user", "restart", "filter-chain.service"])
    eq_default = handoff.index(["pactl", "set-default-sink", "X EQ"])
    assert ["pactl", "set-default-sink", "alsa_speaker"] not in handoff
    assert restart < eq_default
    assert fake._link_target == "alsa_speaker"


def test_route_handoff_stages_eq_before_republishing_it(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    checkpoint = len(fake.calls)

    assert eq.ensure_sink([0] * 10) is True

    handoff = fake.calls[checkpoint:]
    stage = handoff.index(["pactl", "set-sink-volume", "X EQ", "100%"])
    switch = handoff.index(["pactl", "set-default-sink", "X EQ"])
    commit = handoff.index(["pactl", "set-sink-volume", "X EQ", "40%"])
    pin = handoff.index([
        "pactl", "set-sink-volume", "bluez_output.headset", "100%"
    ])
    assert stage < switch < commit < pin
    assert eq._route_state()["sink"] == "bluez_output.headset"


def test_eq_default_route_handoff_restores_old_sink_after_restart(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    checkpoint = len(fake.calls)

    assert eq.ensure_sink([0] * 10) is True

    handoff = fake.calls[checkpoint:]
    restart = handoff.index([
        "systemctl", "--user", "restart", "filter-chain.service"
    ])
    restore = handoff.index([
        "pactl", "set-sink-volume", "alsa_speaker", "40%"
    ])
    assert restart < restore


def test_route_handoff_fails_honestly_when_target_link_is_not_confirmed(tmp_path):
    fake = _FakeRunner()
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    assert eq.ensure_sink([0] * 10) is True

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    checkpoint = len(fake.calls)
    fake._configured_target = None
    run = eq._runner

    def keep_stale_link(argv, timeout=8):
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake.calls.append(argv)
            fake._service_generation += 1
            return ""
        return run(argv, timeout)

    eq._runner = keep_stale_link

    assert eq.ensure_sink([0] * 10) is False

    handoff = fake.calls[checkpoint:]
    assert ["systemctl", "--user", "restart", "filter-chain.service"] in handoff
    assert fake._default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "target_link_not_confirmed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
    }


def test_output_change_during_apply_aborts_before_restarting_old_target(tmp_path):
    fake = _FakeRunner()
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    def change_output_while_writing(*_args, **_kwargs):
        fake._default = "alsa_output.hdmi"
        return True

    eq._write_conf = change_output_while_writing

    assert eq.ensure_sink([0] * 10) is False

    assert ["systemctl", "--user", "restart", "filter-chain.service"] not in fake.calls
    assert not os.path.exists(eq._conf_path())
    assert not os.path.exists(f"{eq._conf_path()}.first-enable-pending")
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "downstream_changed",
        "downstream": "alsa_speaker",
        "current": "alsa_output.hdmi",
    }


def test_ensure_sink_uses_only_the_canonical_pactl_default_write(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None

    assert eq.ensure_sink([0] * 10) is True
    assert ["pactl", "set-default-sink", "X EQ"] in fake.calls
    assert not any(
        call[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ]
        for call in fake.calls
    )


def test_default_probe_uses_short_subprocess_timeouts(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    timeouts = []

    def bounded_runner(argv, timeout=8):
        if argv[0] in ("pactl", "pw-metadata"):
            timeouts.append(timeout)
        return fake(argv, timeout)

    eq._runner = bounded_runner

    assert eq._set_default_confirmed("X EQ", "alsa_speaker") is True
    assert timeouts
    assert max(timeouts) <= 1


def test_default_probe_has_a_finite_end_to_end_budget(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    now = {"value": 0.0}

    eq._monotonic = lambda: now["value"]
    run = eq._runner

    def reject_default(argv, timeout=8):
        now["value"] += 3.0
        if argv == ["pactl", "set-default-sink", "X EQ"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = reject_default

    assert eq._set_default_confirmed("X EQ", "alsa_speaker") is False
    assert eq._default_failure == {
        "reason": "default_confirmation_timeout",
        "current": "alsa_speaker",
    }
    assert fake.calls.count(["pactl", "set-default-sink", "X EQ"]) < 5


def test_ensure_sink_journals_physical_output_before_configured_default_is_eq(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    assert eq.ensure_sink([0] * 10) is True
    assert fake._configured_default == "X EQ"
    assert eq._route_state() == {
        "sink": "alsa_speaker",
        "volume": "40%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": False,
        "pending_restores": [],
    }


def test_empty_readbacks_never_confirm_bypass_or_sink_absence(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._sleep = lambda _delay: None
    eq._runner = lambda _argv, timeout=8: ""

    assert eq._bypass_eq_default("alsa_speaker") is False
    assert eq._sink_absent_confirmed("X EQ") is False


def test_ensure_sink_default_confirmation_retry_is_bounded(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def never_confirm(argv, timeout=8):
        if argv == ["pactl", "set-default-sink", "X EQ"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = never_confirm

    assert eq.ensure_sink([0] * 10) is False
    assert fake.calls.count(["pactl", "set-default-sink", "X EQ"]) == 3


def test_failed_restart_does_not_publish_new_curve_or_restart_again_immediately(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._monotonic = lambda: 100.0
    run = eq._runner

    def fail_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            fake.calls.append(argv)
            return "failed"
        return run(argv, timeout)

    eq._runner = fail_restart

    assert eq.ensure_sink([3] * 10) is False
    restarts = fake.calls.count(["systemctl", "--user", "restart", "filter-chain.service"])
    assert eq.is_active() is False
    assert eq.apply_diagnostics()["reason"] == "service_restart_failed"

    assert eq.ensure_sink([3] * 10) is False
    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == restarts
    assert eq.apply_diagnostics()["reason"] == "service_restart_backoff"


def test_noop_restart_does_not_publish_a_new_curve(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    assert eq.ensure_sink([0] * 10) is True
    run = eq._runner

    def ignore_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_restart

    assert eq.ensure_sink([3] * 10) is False
    assert eq.apply_diagnostics()["reason"] == "service_restart_failed"


def test_missing_restart_token_before_a_noop_fails_closed(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    reads = 0
    run = eq._runner

    def missing_before(argv, timeout=8):
        nonlocal reads
        if argv == [
            "systemctl",
            "--user",
            "show",
            "filter-chain.service",
            "--property=InvocationID",
            "--property=MainPID",
            "--value",
        ]:
            reads += 1
            if reads == 1:
                fake.calls.append(argv)
                return ""
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = missing_before

    assert eq._restart() is False


def test_restart_retry_budget_is_finite_for_an_unchanged_request(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    run = eq._runner

    def fail_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            fake.calls.append(argv)
            return "failed"
        return run(argv, timeout)

    eq._runner = fail_restart

    for _ in range(10):
        assert eq.ensure_sink([3] * 10) is False
        now["value"] += 120

    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == 3
    assert eq.apply_diagnostics()["reason"] == "service_restart_retry_exhausted"

    restarts = fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    )

    def lose_service_readback(argv, timeout=8):
        if argv[:3] == ["systemctl", "--user", "show"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = lose_service_readback
    assert eq.ensure_sink([3] * 10) is False
    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == restarts


def test_default_confirmation_failure_has_one_finite_retry_budget(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    run = eq._runner

    def reject_eq_default(argv, timeout=8):
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ] or argv == ["pactl", "set-default-sink", "X EQ"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = reject_eq_default

    for _ in range(10):
        assert eq.ensure_sink([0] * 10) is False
        now["value"] += 120

    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == 1
    assert fake.calls.count(["pactl", "set-default-sink", "X EQ"]) == 9
    assert eq.apply_diagnostics()["reason"] == "default_sink_retry_exhausted"


def test_link_readback_failure_does_not_restart_same_config_repeatedly(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def hide_links(argv, timeout=8):
        if argv == ["pw-link", "-l"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = hide_links

    assert eq.ensure_sink([0] * 10) is False
    restarts = fake.calls.count(["systemctl", "--user", "restart", "filter-chain.service"])
    assert eq.ensure_sink([0] * 10) is False
    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == restarts


def test_support_requires_pw_link_for_route_readback(monkeypatch):
    monkeypatch.setattr(pipewire, "filter_chain_module", lambda: "/lib/filter-chain.so")
    monkeypatch.setattr(pipewire, "resolve_bin", lambda name: name)
    monkeypatch.setattr(pipewire.shutil, "which", lambda _name: None)
    eq = PipeWireEq(runner=_FakeRunner(), name="X")
    eq._session = (1000, "/run/user/1000", "deck")

    assert eq.is_supported() is False


def test_support_requires_pactl_for_confirmed_handoffs(monkeypatch):
    monkeypatch.setattr(pipewire, "filter_chain_module", lambda: "/lib/filter-chain.so")
    eq = PipeWireEq(runner=_FakeRunner(), name="X")
    eq._session = (1000, "/run/user/1000", "deck")
    eq._binary_available = lambda name: name != "pactl"

    assert eq.is_supported() is False


def test_support_accepts_tools_resolved_outside_the_process_path(monkeypatch):
    monkeypatch.setattr(pipewire, "filter_chain_module", lambda: "/lib/filter-chain.so")
    monkeypatch.setattr(pipewire, "resolve_bin", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(pipewire.shutil, "which", lambda _name: None)
    eq = PipeWireEq(runner=_FakeRunner(), name="X")
    eq._session = (1000, "/run/user/1000", "deck")

    assert eq.is_supported() is True


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
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ] or argv == ["pactl", "set-default-sink", "X EQ"]:
            fake.calls.append(argv)
            return ""
        return fake(argv, timeout)

    eq._runner = ignore_default_change

    assert eq.ensure_sink([0] * 10) is False

    assert fake.volume_sets("alsa_speaker") == [
        ["pactl", "set-sink-volume", "alsa_speaker", "40%"],
    ]
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "default_sink_not_confirmed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
        "current": "alsa_speaker",
    }


def test_failed_first_enable_rolls_back_and_retry_preserves_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    conf = eq._conf_path()
    eq._write_conf = lambda *a, **k: Path(conf).write_text("x") > 0
    block_default = {"enabled": True}
    run = eq._runner

    def fail_first_default_change(argv, timeout=8):
        targets_eq = (
            argv[:5]
            == ["pw-metadata", "-n", "default", "0", "default.audio.sink"]
            or argv == ["pactl", "set-default-sink", "X EQ"]
        )
        if targets_eq and block_default["enabled"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = fail_first_default_change

    assert eq.ensure_sink([0] * 10) is False
    assert Path(conf).exists()
    assert eq._route_state()["phase"] == "prepared"
    block_default["enabled"] = False
    now["value"] += 16
    assert eq.ensure_sink([0] * 10) is True

    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "100%"],
        ["pactl", "set-sink-volume", "X EQ", "100%"],
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]
    assert fake.volume_sets("alsa_speaker") == [
        ["pactl", "set-sink-volume", "alsa_speaker", "40%"],
        ["pactl", "set-sink-volume", "alsa_speaker", "100%"],
    ]


def test_first_enable_restart_retry_still_carries_the_physical_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    run = eq._runner

    def fail_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            fake.calls.append(argv)
            return "failed"
        return run(argv, timeout)

    eq._runner = fail_restart
    assert eq.ensure_sink([0] * 10) is False

    eq._runner = run
    now["value"] += 16
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "100%"],
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]


def test_first_enable_volume_handoff_survives_a_process_restart(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    run = eq._runner

    def fail_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            fake.calls.append(argv)
            return "failed"
        return run(argv, timeout)

    eq._runner = fail_restart
    assert eq.ensure_sink([0] * 10) is False

    recovered_fake = _FakeRunner(downstream_vol="100%")
    recovered = _make_eq(tmp_path, recovered_fake, conf_exists=True)
    assert recovered.ensure_sink([0] * 10) is True
    assert recovered_fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "100%"],
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]


def test_disable_after_failed_first_enable_does_not_change_physical_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf = eq._conf_path()
    eq._write_conf = lambda *a, **k: Path(conf).write_text("x") > 0

    def ignore_default_change(argv, timeout=8):
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ] or argv == ["pactl", "set-default-sink", "X EQ"]:
            fake.calls.append(argv)
            return ""
        return fake(argv, timeout)

    eq._runner = ignore_default_change
    assert eq.ensure_sink([0] * 10) is False

    eq.teardown()

    assert fake.volume_sets("alsa_speaker")[-1] == [
        "pactl", "set-sink-volume", "alsa_speaker", "40%"
    ]
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


def test_active_state_drops_when_eq_output_is_linked_to_another_sink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._link_target = "bluez_output.wrong"

    assert eq.is_active() is False


def test_failed_changed_curve_invalidates_previous_active_state(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    eq._write_conf = lambda *args, **kwargs: False

    assert eq.ensure_sink([3] * 10) is False

    assert eq.is_active() is False
    assert fake._default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "config_write_failed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
    }


def test_config_write_exception_bypasses_the_previous_eq(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    def fail_write(*_args, **_kwargs):
        raise OSError("disk unavailable")

    eq._write_conf = fail_write

    assert eq.ensure_sink([3] * 10) is False

    assert fake._default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "config_write_failed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
        "error": "OSError",
    }


def test_interrupted_first_config_write_is_safe_across_process_restart(
    tmp_path, monkeypatch
):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)
    replace = os.replace
    attempts = 0

    def interrupt_first_replace(source, destination, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("interrupted write")
        return replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", interrupt_first_replace)

    assert eq.ensure_sink([0] * 10) is False
    assert not os.path.exists(eq._conf_path())
    assert not os.path.exists(f"{eq._conf_path()}.pending")
    assert fake._default == "alsa_speaker"

    recovered = _make_eq(tmp_path, fake, conf_exists=False)
    recovered._write_conf = PipeWireEq._write_conf.__get__(recovered, PipeWireEq)
    assert recovered.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ")[-1] == [
        "pactl",
        "set-sink-volume",
        "X EQ",
        "40%",
    ]


def test_first_enable_volume_survives_a_crash_after_config_publish(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    real_write = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    def crash_after_publish(*args, **kwargs):
        assert real_write(*args, **kwargs) is True
        raise RuntimeError("process terminated")

    eq._write_conf = crash_after_publish

    crashed = False
    try:
        eq.ensure_sink([0] * 10)
    except RuntimeError:
        crashed = True
    assert crashed is True
    assert os.path.exists(eq._conf_path())
    assert os.path.exists(f"{eq._conf_path()}.first-enable-pending")

    recovered = _make_eq(tmp_path, fake, conf_exists=True)
    assert recovered.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ")[-1] == [
        "pactl",
        "set-sink-volume",
        "X EQ",
        "40%",
    ]
    assert recovered._route_state()["phase"] == "active"


def test_first_enable_rejects_a_crash_marker_from_another_output(tmp_path):
    fake = _FakeRunner(
        downstream_vol={"alsa_speaker": "40%", "alsa_output.hdmi": "20%"}
    )
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    real_write = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    def change_output_and_crash(*args, **kwargs):
        assert real_write(*args, **kwargs) is True
        fake._default = "alsa_output.hdmi"
        raise RuntimeError("process terminated")

    eq._write_conf = change_output_and_crash

    try:
        eq.ensure_sink([0] * 10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected simulated process termination")

    recovered = _make_eq(tmp_path, fake, conf_exists=True)
    assert recovered.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ")[-1] == [
        "pactl",
        "set-sink-volume",
        "X EQ",
        "20%",
    ]


def test_failed_config_removal_keeps_the_route_scoped_volume_marker(
    tmp_path, monkeypatch
):
    fake = _FakeRunner(
        downstream_vol={"alsa_speaker": "40%", "alsa_output.hdmi": "20%"}
    )
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tIDLE\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf_path = eq._conf_path()
    writes = 0

    def write_and_change_output(*args, **kwargs):
        nonlocal writes
        writes += 1
        Path(conf_path).write_text("x")
        fake._configured_target = kwargs.get("downstream") or args[-1]
        if writes == 1:
            fake._default = "alsa_output.hdmi"
        return True

    eq._write_conf = write_and_change_output
    remove_entry = eq._remove_entry

    def reject_config_removal(path):
        if path == conf_path:
            return False
        return remove_entry(path)

    monkeypatch.setattr(eq, "_remove_entry", reject_config_removal)

    assert eq.ensure_sink([0] * 10) is False
    assert os.path.exists(conf_path)
    assert os.path.exists(f"{conf_path}.first-enable-pending")

    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ")[-1] == [
        "pactl",
        "set-sink-volume",
        "X EQ",
        "20%",
    ]


def test_route_state_cleanup_failure_is_retained_until_teardown_can_retry(
    tmp_path, monkeypatch
):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    marker_path = f"{eq._conf_path()}.first-enable-pending"
    remove_entry = eq._remove_entry

    def reject_marker_removal(path):
        if path == marker_path:
            return False
        return remove_entry(path)

    monkeypatch.setattr(eq, "_remove_entry", reject_marker_removal)

    assert eq.ensure_sink([0] * 10) is True
    assert fake._default == "X EQ"
    assert os.path.exists(marker_path)
    assert eq.teardown() is False
    assert fake._default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "teardown_marker_cleanup_failed",
        "downstream": "alsa_speaker",
    }

    monkeypatch.setattr(eq, "_remove_entry", remove_entry)
    now["value"] += 120
    assert eq.teardown() is True
    assert not os.path.exists(marker_path)


def test_config_write_failure_has_one_finite_retry_budget(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    writes = []
    eq._write_conf = lambda *_args, **_kwargs: writes.append(True) and False

    for _ in range(10):
        assert eq.ensure_sink([3] * 10) is False
        now["value"] += 120

    assert len(writes) == 3
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "config_write_retry_exhausted",
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


def test_teardown_without_runtime_reports_pending_marker_cleanup_failure(
    tmp_path, monkeypatch
):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    marker_path = eq._pending_path()
    Path(marker_path).write_text('{"sink":"alsa_speaker","volume":"40%"}')
    remove_entry = eq._remove_entry

    def reject_marker_removal(path):
        if path == marker_path:
            return False
        return remove_entry(path)

    monkeypatch.setattr(eq, "_remove_entry", reject_marker_removal)

    assert eq.teardown() is False
    assert Path(marker_path).exists()
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "teardown_marker_cleanup_failed",
        "downstream": "alsa_speaker",
    }
    assert ["systemctl", "--user", "restart", "filter-chain.service"] not in fake.calls


def test_teardown_reports_marker_failure_after_restoring_audio(tmp_path, monkeypatch):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    marker_path = eq._pending_path()
    Path(marker_path).write_text('{"sink":"alsa_speaker","volume":"40%"}')
    remove_entry = eq._remove_entry

    def reject_marker_removal(path):
        if path == marker_path:
            return False
        return remove_entry(path)

    monkeypatch.setattr(eq, "_remove_entry", reject_marker_removal)

    assert eq.teardown() is False
    assert fake._default == "alsa_speaker"
    assert "\tX EQ\t" not in fake._sinks
    assert Path(marker_path).exists()
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "teardown_marker_cleanup_failed",
        "downstream": "alsa_speaker",
    }


def test_teardown_failure_bypasses_eq_and_retains_state_for_cleanup_retry(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    run = eq._runner

    def ignore_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_restart

    assert eq.teardown() is False
    assert fake._default == "alsa_speaker"
    assert eq._orig_default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "teardown_restart_failed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
    }


def test_teardown_cleans_a_persisted_eq_from_a_fresh_process(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    fake._default = "X EQ"
    fake._configured_default = "alsa_speaker"
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    eq = _make_eq(tmp_path, fake, conf_exists=True)

    assert eq.teardown() is True
    assert fake._default == "alsa_speaker"
    assert "\tX EQ\t" not in fake._sinks


def test_fresh_process_recovers_target_from_its_config_without_a_live_link(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "alsa_output.hdmi": "65%",
        "X EQ": "65%",
    })
    fake._default = "X EQ"
    fake._configured_default = "X EQ"
    fake._link_target = ""
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._conf_path()).write_text('target.object = "alsa_output.hdmi"')

    assert eq._downstream_sink() == "alsa_output.hdmi"
    assert eq.teardown() is True
    assert fake._default == "alsa_output.hdmi"


def test_fresh_process_rejects_ambiguous_targets_instead_of_guessing(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "alsa_output.hdmi": "65%",
        "X EQ": "40%",
    })
    fake._default = "X EQ"
    fake._configured_default = "X EQ"
    fake._link_target = ""
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\talsa_output.hdmi\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._conf_path()).write_text("invalid")

    assert eq._downstream_sink() is None
    assert eq.teardown() is False
    assert fake._default == "X EQ"


def test_teardown_hands_off_volume_and_default_before_removing_eq(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    checkpoint = len(fake.calls)

    assert eq.teardown() is True

    teardown = fake.calls[checkpoint:]
    volume = teardown.index([
        "pactl", "set-sink-volume", "alsa_speaker", "40%"
    ])
    default = teardown.index(["pactl", "set-default-sink", "alsa_speaker"])
    restart = teardown.index([
        "systemctl", "--user", "restart", "filter-chain.service"
    ])
    assert volume < default < restart


def test_fresh_teardown_prefers_pending_volume_over_staged_eq_volume(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "X EQ": "100%",
    })
    fake._default = "X EQ"
    fake._configured_default = "alsa_speaker"
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(
        '{"sink":"alsa_speaker","volume":"40%","phase":"prepared",'
        '"muted":false,"physical_volumes":["40%"],"physical_muted":false}'
    )

    assert eq.teardown() is True
    assert fake._default == "alsa_speaker"
    assert fake.volume_sets("alsa_speaker")[-1] == [
        "pactl",
        "set-sink-volume",
        "alsa_speaker",
        "40%",
    ]
    assert not Path(eq._pending_path()).exists()


def test_teardown_removes_an_orphan_eq_sink_without_a_config_file(tmp_path):
    fake = _FakeRunner()
    fake._sinks += "3\tX EQ\tPipeWire\t...\tIDLE\n"
    eq = _make_eq(tmp_path, fake, conf_exists=False)

    assert eq.teardown() is True
    assert fake.calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == 1
    assert "\tX EQ\t" not in fake._sinks


def test_orphan_cleanup_retries_after_the_config_was_removed(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    fake._default = "X EQ"
    fake._configured_default = "alsa_speaker"
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    run = eq._runner

    def ignore_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_restart
    assert eq.teardown() is False
    assert fake._default == "alsa_speaker"

    eq._runner = run
    now["value"] += 16
    assert eq.teardown() is True
    assert "\tX EQ\t" not in fake._sinks


def test_teardown_retry_budget_is_finite(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    run = eq._runner
    checkpoint = len(fake.calls)

    def fail_restart(argv, timeout=8):
        if argv == ["systemctl", "--user", "is-active", "filter-chain.service"]:
            fake.calls.append(argv)
            return "failed"
        return run(argv, timeout)

    eq._runner = fail_restart

    for _ in range(10):
        assert eq.teardown() is False
        now["value"] += 120

    calls = fake.calls[checkpoint:]
    assert calls.count(
        ["systemctl", "--user", "restart", "filter-chain.service"]
    ) == 3
    assert eq.apply_diagnostics()["reason"] == "teardown_retry_exhausted"


def test_teardown_rejects_a_restarted_service_that_still_exposes_eq_sink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    fake._keep_eq_on_restart = True
    eq._sleep = lambda _delay: None

    assert eq.teardown() is False
    assert eq.apply_diagnostics()["reason"] == "teardown_sink_still_present"


def test_teardown_does_not_publish_success_without_default_handoff(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    run = eq._runner

    def reject_physical_default(argv, timeout=8):
        if argv == ["pactl", "set-default-sink", "alsa_speaker"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = reject_physical_default

    assert eq.teardown() is False
    assert eq._orig_default == "alsa_speaker"
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "teardown_default_not_confirmed",
        "downstream": "alsa_speaker",
    }


def test_route_state_rejects_schema_without_physical_ownership(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    Path(eq._pending_path()).write_text(
        '{"sink":"alsa_speaker","volume":"40%",'
        '"phase":"active","muted":true}'
    )

    assert eq._route_state() is None
    assert fake.volume_sets("alsa_speaker") == []


def test_route_state_migrates_the_original_two_field_journal(tmp_path):
    fake = _FakeRunner()
    fake._default = "X EQ"
    fake._mutes["X EQ"] = True
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    Path(eq._pending_path()).write_text(
        '{"sink":"alsa_speaker","volume":"40%"}'
    )

    assert eq._route_state() == {
        "sink": "alsa_speaker",
        "volume": "40%",
        "phase": "prepared",
        "muted": True,
        "physical_volumes": ["40%"],
        "physical_muted": False,
        "pending_restores": [],
    }


def test_two_field_journal_uses_live_physical_channels_and_default_mute(tmp_path):
    fake = _FakeRunner()
    fake._volume_channels["alsa_speaker"] = ("35%", "45%")
    fake._mutes["alsa_speaker"] = True
    fake._mutes["X EQ"] = False
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    Path(eq._pending_path()).write_text(
        '{"sink":"alsa_speaker","volume":"35%"}'
    )

    state = eq._route_state()
    assert state["muted"] is True
    assert state["physical_volumes"] == ["35%", "45%"]
    assert state["physical_muted"] is True


def test_route_state_rejects_incomplete_ownership_data(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    Path(eq._pending_path()).write_text(
        '{"sink":"alsa_speaker","volume":"40%","phase":"active"}'
    )

    assert eq._route_state() is None


def test_pin_aborts_before_mutation_without_a_complete_snapshot(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    run = eq._runner

    def omit_mute(argv, timeout=8):
        if argv == ["pactl", "get-sink-mute", "alsa_speaker"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = omit_mute

    assert eq._pin_downstream("alsa_speaker", 0) is False
    assert fake.volume_sets("alsa_speaker") == []


def test_restore_retains_ownership_until_readback_confirms_it(tmp_path):
    fake = _FakeRunner(downstream_vol="100%")
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._downstream_volumes["alsa_speaker"] = ("40%",)
    eq._downstream_mutes["alsa_speaker"] = True
    run = eq._runner

    def ignore_restore(argv, timeout=8):
        if argv == ["pactl", "set-sink-volume", "alsa_speaker", "40%"]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_restore

    assert eq._restore_downstream("alsa_speaker") is False
    assert eq._downstream_volumes["alsa_speaker"] == ("40%",)
    assert eq._downstream_mutes["alsa_speaker"] is True


def test_active_reapply_refreshes_live_volume_and_mute_in_the_journal(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True

    assert eq.ensure_sink([0] * 10) is True
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True
    assert eq._route_state()["physical_volumes"] == ["40%"]


def test_active_state_sync_refreshes_live_volume_and_mute(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True

    assert eq.sync_state() is True
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True
    assert eq._route_state()["physical_volumes"] == ["40%"]


def test_active_state_sync_restores_a_replugged_old_sink(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "bluez_output.headset": "100%",
        "X EQ": "25%",
    })
    fake._default = "X EQ"
    fake._link_target = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "bluez_output.headset",
        "volume": "25%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["65%"],
        "physical_muted": False,
        "pending_restores": [{
            "sink": "alsa_speaker",
            "volumes": ["40%"],
            "muted": True,
        }],
    }))

    assert eq.sync_state() is True
    assert fake._volumes["alsa_speaker"] == "40%"
    assert fake._mutes["alsa_speaker"] is True
    assert fake._volumes["bluez_output.headset"] == "100%"
    assert eq._route_state()["pending_restores"] == []


def test_curve_restart_restores_journaled_eq_volume_and_mute(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True
    run = eq._runner

    def reset_eq_controls_on_restart(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake._volumes["X EQ"] = "100%"
            fake._volume_channels["X EQ"] = ("100%",)
            fake._mutes["X EQ"] = False
        return result

    eq._runner = reset_eq_controls_on_restart

    assert eq.ensure_sink([1] * 10) is True
    assert fake._volumes["X EQ"] == "25%"
    assert fake._mutes["X EQ"] is True
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True


def test_route_restart_preserves_live_state_newer_than_journal(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    run = eq._runner

    def reset_eq_controls_on_restart(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake._volumes["X EQ"] = "100%"
            fake._volume_channels["X EQ"] = ("100%",)
            fake._mutes["X EQ"] = False
        return result

    eq._runner = reset_eq_controls_on_restart

    assert eq.ensure_sink([0] * 10) is True
    assert fake._volumes["X EQ"] == "25%"
    assert fake._mutes["X EQ"] is True
    assert eq._route_state()["sink"] == "bluez_output.headset"
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True


def test_curve_restart_crash_recovers_prepared_eq_volume_and_mute(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True
    assert eq.sync_state() is True
    restart = eq._restart

    def crash_after_restart():
        assert restart() is True
        fake._volumes["X EQ"] = "100%"
        fake._volume_channels["X EQ"] = ("100%",)
        fake._mutes["X EQ"] = False
        raise RuntimeError("process terminated")

    eq._restart = crash_after_restart

    try:
        eq.ensure_sink([1] * 10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected simulated process termination")

    assert eq._route_state()["phase"] == "prepared"
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True

    recovered = _make_eq(tmp_path, fake, conf_exists=True)

    assert recovered.ensure_sink([1] * 10) is True
    assert fake._volumes["X EQ"] == "25%"
    assert fake._mutes["X EQ"] is True


def test_activation_rejects_a_missing_final_mute_readback(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    run = eq._runner
    reads = {"eq_mute": 0}

    def lose_final_mute(argv, timeout=8):
        if argv == ["pactl", "get-sink-mute", "X EQ"]:
            reads["eq_mute"] += 1
            if reads["eq_mute"] == 2:
                fake.calls.append(argv)
                return ""
        return run(argv, timeout)

    eq._runner = lose_final_mute

    assert eq.ensure_sink([0] * 10) is False
    assert eq.apply_diagnostics()["reason"] == "route_state_write_failed"


def test_fresh_backend_preserves_live_eq_state_and_physical_snapshot(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._sinks += "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    fake._volumes["X EQ"] = "25%"
    fake._volume_channels["X EQ"] = ("25%",)
    fake._mutes["X EQ"] = True

    recovered = _make_eq(tmp_path, fake, conf_exists=True)

    assert recovered.ensure_sink([0] * 10) is True
    state = recovered._route_state()
    assert state["volume"] == "25%"
    assert state["muted"] is True
    assert state["physical_volumes"] == ["40%"]
    assert state["physical_muted"] is False


def test_upgrade_without_journal_captures_live_eq_before_restart(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "X EQ": "25%",
    })
    fake._default = "X EQ"
    fake._link_target = "alsa_speaker"
    fake._mutes["X EQ"] = True
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    run = eq._runner

    def reset_eq_controls_on_restart(argv, timeout=8):
        result = run(argv, timeout)
        if argv == ["systemctl", "--user", "restart", "filter-chain.service"]:
            fake._volumes["X EQ"] = "100%"
            fake._volume_channels["X EQ"] = ("100%",)
            fake._mutes["X EQ"] = False
        return result

    eq._runner = reset_eq_controls_on_restart

    assert eq.ensure_sink([0] * 10) is True
    assert fake._volumes["X EQ"] == "25%"
    assert fake._mutes["X EQ"] is True
    assert eq._route_state()["volume"] == "25%"
    assert eq._route_state()["muted"] is True


def test_journal_only_teardown_restores_last_active_user_state(tmp_path):
    fake = _FakeRunner(downstream_vol="100%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "alsa_speaker",
        "volume": "25%",
        "phase": "active",
        "muted": True,
        "physical_volumes": ["40%"],
        "physical_muted": False,
        "pending_restores": [],
    }))

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "25%"
    assert fake._mutes["alsa_speaker"] is True
    assert not Path(eq._pending_path()).exists()


def test_fresh_teardown_restores_owned_sink_after_external_default_change(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "bluez_output.headset": "65%",
        "X EQ": "25%",
    })
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "alsa_speaker",
        "volume": "25%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": True,
        "pending_restores": [],
    }))

    assert eq.teardown() is True
    assert fake._default == "bluez_output.headset"
    assert fake._volumes["alsa_speaker"] == "40%"
    assert fake._mutes["alsa_speaker"] is True
    assert not Path(eq._pending_path()).exists()


def test_fresh_teardown_transfers_state_when_owned_sink_is_already_default(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "X EQ": "25%",
    })
    fake._default = "alsa_speaker"
    fake._mutes["X EQ"] = True
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tIDLE\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "alsa_speaker",
        "volume": "40%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": False,
        "pending_restores": [],
    }))

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "25%"
    assert fake._mutes["alsa_speaker"] is True
    assert not Path(eq._pending_path()).exists()


def test_fresh_teardown_retains_unplugged_owned_sink_until_replug(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "bluez_output.headset": "65%",
        "X EQ": "25%",
    })
    fake._default = "bluez_output.headset"
    fake._sinks = (
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "alsa_speaker",
        "volume": "25%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": True,
        "pending_restores": [],
    }))

    assert eq.teardown() is False
    assert eq._route_state()["pending_restores"] == [{
        "sink": "alsa_speaker",
        "volumes": ["40%"],
        "muted": True,
    }]

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
    )
    eq._monotonic = lambda: 100.0

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "40%"
    assert fake._mutes["alsa_speaker"] is True
    assert not Path(eq._pending_path()).exists()


def test_fresh_eq_teardown_retains_unplugged_link_target_until_replug(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "100%",
        "bluez_output.headset": "65%",
        "X EQ": "25%",
    })
    fake._default = "X EQ"
    fake._link_target = "alsa_speaker"
    fake._sinks = (
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    Path(eq._pending_path()).write_text(json.dumps({
        "sink": "alsa_speaker",
        "volume": "25%",
        "phase": "active",
        "muted": False,
        "physical_volumes": ["40%"],
        "physical_muted": True,
        "pending_restores": [],
    }))

    assert eq.teardown() is False
    assert fake._default == "bluez_output.headset"
    assert eq._route_state()["pending_restores"][0]["sink"] == "alsa_speaker"

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
    )
    eq._monotonic = lambda: 100.0

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "40%"
    assert fake._mutes["alsa_speaker"] is True
    assert not Path(eq._pending_path()).exists()


def test_route_handoff_recovers_after_crash_before_new_journal(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    persist = eq._persist_route_state

    def crash_before_new_journal(downstream, *args):
        if downstream == "bluez_output.headset":
            raise RuntimeError("process terminated")
        return persist(downstream, *args)

    eq._persist_route_state = crash_before_new_journal

    try:
        eq.ensure_sink([0] * 10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected simulated process termination")

    assert fake._volumes["alsa_speaker"] == "100%"
    assert eq._route_state()["sink"] == "alsa_speaker"

    recovered = _make_eq(tmp_path, fake, conf_exists=True)

    assert recovered.ensure_sink([0] * 10) is True
    assert fake._volumes["alsa_speaker"] == "40%"
    assert recovered._route_state()["sink"] == "bluez_output.headset"
    assert recovered._route_state()["physical_volumes"] == ["65%"]


def test_eq_default_route_handoff_journals_target_before_pin(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tIDLE\n"
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    persist = eq._persist_route_state

    def crash_after_target_pin(
        downstream,
        volume,
        phase,
        muted,
        physical_volumes,
        physical_muted,
    ):
        if downstream == "bluez_output.headset" and phase == "active":
            raise RuntimeError("process terminated")
        return persist(
            downstream,
            volume,
            phase,
            muted,
            physical_volumes,
            physical_muted,
        )

    eq._persist_route_state = crash_after_target_pin

    try:
        eq.ensure_sink([0] * 10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected simulated process termination")

    state = eq._route_state()
    assert state["sink"] == "bluez_output.headset"
    assert state["phase"] == "prepared"
    assert state["physical_volumes"] == ["65%"]

    recovered = _make_eq(tmp_path, fake, conf_exists=True)

    assert recovered.ensure_sink([0] * 10) is True
    assert recovered._route_state()["physical_volumes"] == ["65%"]


def test_hot_unplug_restore_survives_retry_exhaustion_and_replug(tmp_path):
    fake = _FakeRunner(downstream_vol={
        "alsa_speaker": "40%",
        "bluez_output.headset": "65%",
    })
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    assert eq.ensure_sink([0] * 10) is True

    fake._default = "bluez_output.headset"
    fake._configured_default = "bluez_output.headset"
    fake._sinks = (
        "2\tbluez_output.headset\tPipeWire\t...\tRUNNING\n"
        "3\tX EQ\tPipeWire\t...\tRUNNING\n"
    )
    assert eq.ensure_sink([0] * 10) is True
    assert eq._route_state()["pending_restores"] == [{
        "sink": "alsa_speaker",
        "volumes": ["40%"],
        "muted": False,
    }]

    now = {"value": 100.0}
    eq._monotonic = lambda: now["value"]
    assert eq.teardown() is False
    for _attempt in range(4):
        now["value"] += 20
        assert eq.teardown() is False

    fake._sinks = (
        "1\talsa_speaker\tPipeWire\t...\tRUNNING\n"
        "2\tbluez_output.headset\tPipeWire\t...\tIDLE\n"
    )
    now["value"] += 20

    assert eq.teardown() is True
    assert fake._volumes["alsa_speaker"] == "40%"
    assert fake._mutes["alsa_speaker"] is False
    assert not Path(eq._pending_path()).exists()


_PW_LINK = """effect_output.pdc_eq:output_FL
  |-> alsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo:playback_FL
alsa_output.pci-0000_c2_00.6.analog-stereo:playback_FL
  |<- alsa_loopback_stream.alsa_output.pci-0000_c2_00.6.analog-stereo:output_FL
some_unrelated_node:port
  |-> another_unrelated:in
"""


def test_link_reaches_requires_the_eq_output_to_reach_the_expected_sink():
    assert _link_reaches(
        _PW_LINK,
        "effect_output.pdc_eq",
        "alsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo",
    )
    assert not _link_reaches(_PW_LINK, "effect_output.pdc_eq", "bluez_output.headset")


def test_linked_downstream_returns_only_a_current_physical_candidate():
    candidates = [
        "alsa_loopback_device.alsa_output.pci-0000_c2_00.6.analog-stereo",
        "bluez_output.headset",
    ]

    assert _linked_downstream(_PW_LINK, "effect_output.pdc_eq", candidates) == candidates[0]
    assert _linked_downstream(_PW_LINK, "effect_output.pdc_eq", [candidates[1]]) is None


def test_relevant_links_keeps_eq_and_hardware_drops_noise():
    out = _relevant_links(_PW_LINK)
    assert "effect_output.pdc_eq" in out
    assert "alsa_output.pci-0000_c2_00.6" in out
    assert "loopback" in out
    assert "some_unrelated_node" not in out
    assert "|-> alsa_loopback_device" in out


def test_relevant_links_empty_and_capped():
    assert _relevant_links("") == ""
    assert _relevant_links(None) == ""
    big = "\n".join("alsa_output.sink%d:port" % i for i in range(5000))
    assert len(_relevant_links(big, cap=500)) == 500
