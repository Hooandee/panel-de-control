"""#1159 (PDC-Z3JR): ROG Ally RC71L, Bazzite, InputPlumber 0.83.1. Capabilities read 27 at
boot and 22 after every resume, and the running game ignores the pad. The bundle only keeps
the 27 as a count, so the five names lost are placeholders; the 22 left and the version are
the report's own. The probe observes and never writes to the daemon."""
import asyncio
import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from controllers import resume_probe
from controllers.dbus import IpDbus
from controllers.factory import IpBackend
from pdc_report.collector import redact_obj

REPORT_CAPS_AFTER = [
    "Gamepad:Axis:LeftStick", "Gamepad:Axis:RightStick",
    "Gamepad:Button:DPadDown", "Gamepad:Button:DPadLeft", "Gamepad:Button:DPadRight",
    "Gamepad:Button:DPadUp", "Gamepad:Button:East", "Gamepad:Button:Guide",
    "Gamepad:Button:LeftBumper", "Gamepad:Button:LeftStick", "Gamepad:Button:North",
    "Gamepad:Button:RightBumper", "Gamepad:Button:RightStick", "Gamepad:Button:Select",
    "Gamepad:Button:South", "Gamepad:Button:Start", "Gamepad:Button:West",
    "Gamepad:Trigger:LeftTrigger", "Gamepad:Trigger:RightTrigger",
    "Accelerometer:Center", "Gyroscope:Center", "Sync",
]
LOST = [f"Gamepad:Button:Lost{n}" for n in range(1, 6)]
REPORT_CAPS_BEFORE = [*REPORT_CAPS_AFTER, *LOST]


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


class _Bus:
    """busctl as InputPlumber 0.83.1 answers it after the resume; records every call."""

    def __init__(self, caps=REPORT_CAPS_AFTER, composite=7):
        self.caps, self.composite, self.calls = caps, composite, []

    def __call__(self, args):
        self.calls.append(args)
        if args[1] == "tree":
            return _result(f"└─/org/shadowblip/InputPlumber/CompositeDevice{self.composite}\n")
        prop = args[-1]
        if prop == "Capabilities":
            return _result(f"as {len(self.caps)} " + " ".join(f'"{c}"' for c in self.caps))
        if prop == "TargetDevices":
            return _result(
                'as 3 "/org/shadowblip/InputPlumber/devices/target/deck-uhid0" '
                '"/org/shadowblip/InputPlumber/devices/target/mouse0" '
                '"/org/shadowblip/InputPlumber/devices/target/keyboard0"'
            )
        return _result("", 1)


def _machine(tmp_path):
    """The nodes of the report: the Ally MCU and the recreated virtual deck-uhid."""
    dev, sys_root, rules = tmp_path / "dev", tmp_path / "sys", tmp_path / "rules"
    (dev / "input").mkdir(parents=True)
    rules.mkdir()
    for name, mode, hid, virtual in (
        ("hidraw3", 0o000, "0003:00000B05:00001ABE", False),
        ("hidraw4", 0o600, "0003:000028DE:000012FD", True),
    ):
        node = dev / name
        node.write_text("")
        node.chmod(mode)
        base = ("devices/virtual/misc/uhid/" if virtual else "devices/pci0000:00/usb1/") + name
        real = sys_root / base
        (real / "device").mkdir(parents=True)
        (real / "device" / "uevent").write_text(f"HID_ID={hid}\n")
        (sys_root / "class" / "hidraw").mkdir(parents=True, exist_ok=True)
        os.symlink(real, sys_root / "class" / "hidraw" / name)
    (dev / "input" / "event17").write_text("")
    event = sys_root / "devices" / "virtual" / "input" / "input44" / "event17"
    (event / "device" / "id").mkdir(parents=True)
    (event / "device" / "id" / "vendor").write_text("28de\n")
    (event / "device" / "id" / "product").write_text("11ff\n")
    (sys_root / "class" / "input").mkdir(parents=True)
    os.symlink(event, sys_root / "class" / "input" / "event17")
    rule = rules / "96-inputplumber-hide-hidraw3.rules"
    rule.write_text("")
    os.utime(rule, (1_794_139_000, 1_794_139_000))
    (rules / "70-unrelated.rules").write_text("")
    return dev, sys_root, rules


def _collect(tmp_path, bus=None, *, version="0.83.1", device_key="rog_ally", before=REPORT_CAPS_BEFORE):
    dev, sys_root, rules = _machine(tmp_path)
    bus = bus or _Bus()
    result = resume_probe.collect(
        IpDbus(run=bus), before=before, before_path="/org/shadowblip/InputPlumber/CompositeDevice1",
        version=version, device_key=device_key, elapsed_s=20,
        dev_root=str(dev), sys_root=str(sys_root), rules_dir=str(rules),
    )
    return result, bus


def test_report_drop_27_to_22_is_recorded_with_names_and_flagged(tmp_path):
    result, bus = _collect(tmp_path)

    assert len(result["caps_before"]) == 27 and len(result["caps_after"]) == 22
    assert result["caps_lost"] == LOST and result["caps_gained"] == []
    assert (result["composite_before"], result["composite_after"]) == (1, 7)
    assert result["targets"] == ["deck-uhid", "mouse", "keyboard"]
    assert result["advisory"] == {
        "code": "inputplumber_resume_capability_loss",
        "reason": "known_inputplumber_resume_bug",
        "action": "update_inputplumber",
        "installed": "0.83.1",
        "fixed_in": "0.84.0",
        "capabilities_lost": 5,
    }
    assert all(call[1] in ("tree", "get-property") for call in bus.calls)


def test_nodes_and_stale_hide_rules_are_listed_with_ids(tmp_path):
    result, _ = _collect(tmp_path)

    nodes = {f'{row["kind"]}{row["index"]}': row for row in result["nodes"]}
    assert (nodes["hidraw3"]["mode"], nodes["hidraw3"]["id"], nodes["hidraw3"]["hidden"]) == (
        "0000", "0b05:1abe", True)
    assert (nodes["hidraw4"]["id"], nodes["hidraw4"]["virtual"], nodes["hidraw4"]["hidden"]) == (
        "28de:12fd", True, False)
    assert (nodes["event17"]["id"], nodes["event17"]["virtual"]) == ("28de:11ff", True)
    assert {row["owner"] for row in result["nodes"]} <= {"root", "other"}
    assert result["udev_rules"] == [
        {"name": "96-inputplumber-hide-hidrawN.rules", "mtime": 1_794_139_000,
         "kind": "hidraw", "index": 3, "node_present": True},
    ]


def test_hidraw_numbers_grown_by_resumes_stay_readable_after_redaction(tmp_path):
    result, _ = _collect(tmp_path)
    dev, sys_root, rules = tmp_path / "dev", tmp_path / "sys", tmp_path / "rules"
    real = sys_root / "devices" / "pci0000:00" / "usb1" / "hidraw14"
    (real / "device").mkdir(parents=True)
    (real / "device" / "uevent").write_text("HID_ID=0003:00000B05:00001ABE\n")
    os.symlink(real, sys_root / "class" / "hidraw" / "hidraw14")
    (dev / "hidraw14").write_text("")
    (rules / "96-inputplumber-hide-hidraw14.rules").write_text("")
    record = {
        "t": 1.0, "l": "I", "s": "controller", "m": "resume_probe",
        "nodes": resume_probe.nodes(str(dev), str(sys_root)),
        "udev_rules": resume_probe.udev_rules(str(rules), str(dev)),
    }
    bundle = redact_obj({"journal": {"recent": [json.loads(json.dumps(record))], "older": []}})

    kept = bundle["journal"]["recent"][0]
    assert "[serial]" not in json.dumps(kept)
    assert {(row["kind"], row["index"]) for row in kept["nodes"]} >= {("hidraw", 14)}
    rule = next(row for row in kept["udev_rules"] if row["index"] == 14)
    assert (rule["name"], rule["kind"], rule["node_present"]) == (
        "96-inputplumber-hide-hidrawN.rules", "hidraw", True)


@pytest.mark.parametrize("version,device_key,before", [
    ("0.84.0", "rog_ally", REPORT_CAPS_BEFORE),
    ("0.83.1", "legion_go", REPORT_CAPS_BEFORE),
    ("0.83.1", "rog_ally", REPORT_CAPS_AFTER),
    ("0.83.1", "rog_ally", []),
    (None, "rog_ally", REPORT_CAPS_BEFORE),
])
def test_no_advisory_without_ally_old_inputplumber_and_a_real_loss(tmp_path, version, device_key, before):
    result, _ = _collect(tmp_path, version=version, device_key=device_key, before=before)
    assert result["advisory"] is None


def test_unreachable_daemon_is_not_reported_as_a_loss(tmp_path):
    def down(args):
        return _result("", 1)

    dev, sys_root, rules = _machine(tmp_path)
    result = resume_probe.collect(
        IpDbus(run=down), before=REPORT_CAPS_BEFORE, before_path=None, version="0.83.1",
        device_key="rog_ally", dev_root=str(dev), sys_root=str(sys_root), rules_dir=str(rules),
    )
    assert result["caps_read_ok"] is False and result["advisory"] is None
    assert result["caps_lost"] is None and result["caps_gained"] is None
    assert result["composite_after"] is None and result["targets"] is None


def test_unknown_baseline_is_not_compared(tmp_path):
    result, _ = _collect(tmp_path, before=[])
    assert result["before_known"] is False
    assert result["caps_lost"] is None and result["caps_gained"] is None


def test_backend_flag_is_exposed_in_diagnostics_and_sticks(tmp_path):
    result, _ = _collect(tmp_path)
    backend = IpBackend(store=None, dbus=IpDbus(run=_Bus()), version="0.83.1", device_key="rog_ally")
    assert backend.diagnostics()["resume_advisory"] is None

    backend.record_resume_probe(result)
    backend.record_resume_probe({"advisory": None})
    assert backend.diagnostics()["resume_advisory"]["fixed_in"] == "0.84.0"


def test_journal_record_survives_redaction_with_enum_names_and_no_serial_paths(tmp_path):
    result, _ = _collect(tmp_path, before=[*REPORT_CAPS_BEFORE, "Gamepad:Button:LeftPaddle1"])
    record = {"t": 1.0, "l": "W", "s": "controller", "m": "resume_probe", **result}
    bundle = redact_obj({"journal": {"recent": [json.loads(json.dumps(record))], "older": []}})

    kept = bundle["journal"]["recent"][0]
    assert "Gamepad:Button:LeftPaddle1" in kept["caps_before"] and "Gamepad:Button:LeftPaddle1" in kept["caps_lost"]
    assert kept["composite_after"] == 7 and kept["targets"][2] == "keyboard"
    assert "[serial]" not in json.dumps(kept)


def _probe_plugin(tmp_path, monkeypatch, bus):
    from tests.test_gpu_clock_rpc import _make_plugin

    plugin, _ = _make_plugin(tmp_path, monkeypatch)
    import main

    monkeypatch.setattr(main, "_CONTROLLER_RESUME_PROBE_S", 0.0)
    monkeypatch.setattr(main, "IpDbus", lambda *a, **k: IpDbus(run=bus))
    written = []
    monkeypatch.setattr(main.journal, "active", SimpleNamespace(
        write=lambda level, source, message, **fields: written.append((level, source, message, fields))))
    dev, sys_root, rules = _machine(tmp_path)
    real_collect = resume_probe.collect
    monkeypatch.setattr(resume_probe, "collect", lambda dbus, **kw: real_collect(
        dbus, **kw, dev_root=str(dev), sys_root=str(sys_root), rules_dir=str(rules)))

    plugin._init()
    plugin._device = dataclasses.replace(plugin._device, key="rog_ally")
    prior = IpDbus(run=_Bus(REPORT_CAPS_BEFORE, composite=1))
    prior.capabilities()
    plugin._controller = {"manager": "inputplumber", "version": "0.83.1"}
    plugin._controller_backend = IpBackend(
        store=None, dbus=prior, version="0.83.1", device_key="rog_ally")
    return plugin, written


def test_resume_schedules_one_read_only_probe_off_the_loop(tmp_path, monkeypatch):
    bus = _Bus()
    plugin, written = _probe_plugin(tmp_path, monkeypatch, bus)
    bus.calls.clear()

    async def scenario():
        plugin._on_resume_detected(2575)
        await asyncio.sleep(0.3)

    asyncio.run(scenario())

    assert [w[2] for w in written] == ["resume_probe"]
    level, _source, _message, fields = written[0]
    assert level == "WARNING" and fields["caps_lost"] == LOST
    assert all(call[1] in ("tree", "get-property") for call in bus.calls)


def test_inputplumber_silent_at_probe_time_is_info_not_a_loss(tmp_path, monkeypatch):
    plugin, written = _probe_plugin(tmp_path, monkeypatch, lambda args: _result("", 1))

    async def scenario():
        plugin._on_resume_detected(2575)
        await asyncio.sleep(0.3)

    asyncio.run(scenario())

    level, _source, _message, fields = written[0]
    assert level == "INFO" and fields["caps_lost"] is None


def test_shutdown_cancels_a_pending_probe(tmp_path, monkeypatch):
    import main

    plugin, written = _probe_plugin(tmp_path, monkeypatch, _Bus())
    monkeypatch.setattr(main, "_CONTROLLER_RESUME_PROBE_S", 0.05)

    async def scenario():
        plugin._on_resume_detected(2575)
        handle = plugin._controller_resume_probe_handle
        plugin._prepare_shutdown()
        await asyncio.sleep(0.2)
        return handle

    handle = asyncio.run(scenario())
    assert handle.cancelled() and written == []
