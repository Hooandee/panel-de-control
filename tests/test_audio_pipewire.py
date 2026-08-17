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
            volume = self._volumes.get(argv[-1], self._vol)
            return f"Volume: front-left: 26214 / {volume} / ..."
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
    assert fake.volume_sets("X EQ") == [["pactl", "set-sink-volume", "X EQ", "40%"]]
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


def test_first_enable_creates_a_missing_pipewire_config_directory(tmp_path):
    fake = _FakeRunner(downstream_vol="40%")
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    conf = tmp_path / "missing" / "filter-chain.conf.d" / "pdc-eq.conf"
    eq._conf_path = lambda: str(conf)
    fake._conf_path = str(conf)
    eq._write_conf = PipeWireEq._write_conf.__get__(eq, PipeWireEq)

    assert eq.ensure_sink([0] * 10) is True
    assert conf.exists()
    assert not Path(f"{conf}.first-enable-pending").exists()


def test_volume_marker_refuses_to_follow_a_symlink(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    marker = Path(eq._pending_path())
    marker.symlink_to(victim)
    eq._first_enable_downstream = "alsa_speaker"
    eq._first_enable_volume = "40%"

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


def test_ensure_sink_boot_reassert_preserves_user_volume(tmp_path):
    fake = _FakeRunner(downstream_vol="100%")
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    assert eq.ensure_sink([0] * 10) is True
    assert fake.volume_sets("X EQ") == []
    assert ["pactl", "set-sink-volume", "alsa_speaker", "100%"] in fake.calls


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

    eq.teardown()

    assert fake._default == "alsa_speaker"
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
    eq_default = next(
        index
        for index, call in enumerate(handoff)
        if call[:5]
        == ["pw-metadata", "-n", "default", "0", "default.audio.sink"]
    )
    assert ["pactl", "set-default-sink", "alsa_speaker"] not in handoff
    assert restart < eq_default
    assert fake._link_target == "alsa_speaker"


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


def test_ensure_sink_retries_until_default_readback_confirms(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    eq._sleep = lambda _delay: None
    attempts = 0
    run = eq._runner

    def confirm_on_third_attempt(argv, timeout=8):
        nonlocal attempts
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ]:
            attempts += 1
            if attempts < 3:
                fake.calls.append(argv)
                return ""
        return run(argv, timeout)

    eq._runner = confirm_on_third_attempt

    assert eq.ensure_sink([0] * 10) is True
    assert attempts == 3


def test_ensure_sink_sets_effective_default_without_overwriting_configured_output(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=False)
    run = eq._runner

    def metadata_default(argv, timeout=8):
        if argv[:5] == [
            "pw-metadata",
            "-n",
            "default",
            "0",
            "default.audio.sink",
        ]:
            fake.calls.append(argv)
            fake._default = "X EQ"
            return ""
        return run(argv, timeout)

    eq._runner = metadata_default

    assert eq.ensure_sink([0] * 10) is True
    assert not any(
        call[:3] == ["pactl", "set-default-sink", "X EQ"] for call in fake.calls
    )


def test_eq_default_confirmation_never_falls_back_to_pactl(tmp_path):
    fake = _FakeRunner()
    eq = _make_eq(tmp_path, fake, conf_exists=True)
    eq._sleep = lambda _delay: None
    run = eq._runner

    def ignore_metadata_change(argv, timeout=8):
        if argv[:5] == [
            "pw-metadata",
            "-n",
            "default",
            "0",
            "default.audio.sink",
        ]:
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = ignore_metadata_change

    assert eq.ensure_sink([0] * 10) is False
    assert not any(
        call[:3] == ["pactl", "set-default-sink", "X EQ"] for call in fake.calls
    )


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
    attempts = 0
    run = eq._runner

    def never_confirm(argv, timeout=8):
        nonlocal attempts
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ]:
            attempts += 1
            fake.calls.append(argv)
            return ""
        return run(argv, timeout)

    eq._runner = never_confirm

    assert eq.ensure_sink([0] * 10) is False
    assert 1 < attempts <= 6


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
        ]:
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
    assert sum(
        call[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ]
        for call in fake.calls
    ) == 15
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
        ]:
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
        "bypass_confirmed": True,
        "rollback_confirmed": True,
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
        if argv[:5] == [
            "pw-metadata", "-n", "default", "0", "default.audio.sink"
        ]:
            if block_default["enabled"]:
                fake.calls.append(argv)
                return ""
        return run(argv, timeout)

    eq._runner = fail_first_default_change

    assert eq.ensure_sink([0] * 10) is False
    assert not Path(conf).exists()
    block_default["enabled"] = False
    now["value"] += 16
    assert eq.ensure_sink([0] * 10) is True

    assert fake.volume_sets("X EQ") == [
        ["pactl", "set-sink-volume", "X EQ", "40%"],
    ]
    assert fake.volume_sets("alsa_speaker") == [
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
        ]:
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
    assert not os.path.exists(f"{eq._conf_path()}.first-enable-pending")


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


def test_marker_cleanup_failure_bypasses_eq_until_cleanup_can_retry(
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

    assert eq.ensure_sink([0] * 10) is False
    assert fake._default == "alsa_speaker"
    assert os.path.exists(marker_path)
    assert eq.apply_diagnostics() == {
        "ok": False,
        "reason": "pending_marker_cleanup_failed",
        "downstream": "alsa_speaker",
        "bypass_confirmed": True,
    }

    monkeypatch.setattr(eq, "_remove_entry", remove_entry)
    now["value"] += 120
    assert eq.ensure_sink([0] * 10) is True
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
        "downstream": None,
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
