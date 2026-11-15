import json

from pdc_report import hardware_fingerprint
from pdc_report.collector import build_bundle


def _write(root, rel, value):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _machine(root):
    dmi = "sys/class/dmi/id"
    _write(root, f"{dmi}/sys_vendor", "LENOVO\n")
    _write(root, f"{dmi}/product_name", "83E1\n")
    _write(root, f"{dmi}/bios_version", "1.0.0.4\n")
    _write(root, f"{dmi}/product_serial", "PF4ABC123\n")
    _write(root, f"{dmi}/board_serial", "BS9XYZ987\n")
    _write(root, f"{dmi}/product_uuid", "4c4c4544-0042-3510-8051-b4c04f4d3232\n")
    _write(root, "sys/class/drm/card1-eDP-1/status", "connected\n")
    _write(root, "sys/class/drm/card1-eDP-1/modes", "1920x1200\n")
    _write(root, "sys/class/drm/card1-eDP-1/edid", "\x00\xff\xff")
    fw = "sys/class/firmware-attributes/hp-bioscfg/attributes"
    _write(root, f"{fw}/Serial Number/current_value", "5CD1234XYZ\n")
    _write(root, f"{fw}/SvcTag/current_value", "7QK2T93\n")
    _write(root, f"{fw}/System Board CT Number/current_value", "BS9XYZ987\n")
    _write(root, f"{fw}/ppt_pl1_spl/current_value", "15\n")
    _write(root, "sys/class/hwmon/hwmon0/name", "amdgpu\n")
    _write(root, "sys/class/hwmon/hwmon0/temp1_input", "50000\n")
    _write(root, "sys/class/hwmon/hwmon0/device/power/runtime_status", "suspended\n")
    _write(root, "sys/class/hwmon/hwmon1/name", "asus\n")
    _write(root, "sys/class/hwmon/hwmon1/fan1_input", "3200\n")
    _write(root, "etc/os-release", "ID=bazzite\n")
    _write(root, "proc/sys/kernel/osrelease", "6.11.0.1-bazzite\n")
    for mac in ("aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"):
        _write(root, f"sys/class/power_supply/hid-{mac}-battery/model_name", "Ana's Keyboard\n")
        _write(root, f"sys/class/power_supply/hid-{mac}-battery/capacity", "70\n")
        _write(root, f"sys/class/power_supply/hid-{mac}-battery/scope", "Device\n")
    _write(root, "sys/class/power_supply/BAT0/serial_number", "SN12345678\n")
    _write(root, "sys/class/power_supply/BAT0/charge_control_end_threshold", "80\n")
    _write(root, "sys/class/power_supply/BAT0/model_name", "batt aa:bb:cc:dd:ee:ff\n")
    _write(root, "proc/bus/input/devices", (
        'I: Bus=0003 Vendor=17ef Product=6182 Version=0111\n'
        'N: Name="Legion Controller"\nP: Phys=usb-0000:c4:00.0-1/input0\n'
        'U: Uniq=aa:bb:cc:dd:ee:ff\nH: Handlers=event5 js0\n\n'
        'I: Bus=0005 Vendor=054c Product=0ce6 Version=8100\n'
        'N: Name="Ana\'s DualSense"\nH: Handlers=event9\n'
    ))


def test_fingerprint_drops_serials_and_redacts_identifiers_without_shredding_values(tmp_path):
    _machine(tmp_path)

    fingerprint = hardware_fingerprint.collect(
        str(tmp_path), home="/home/ana", hostname="bazzite",
        panel={"tdp": {"ryzenadj": "/home/ana/bin/ryzenadj", "note": "Ana at 192.168.1.20"}})
    text = json.dumps(build_bundle(
        app="pdc", categories=[], text="", environment={}, capabilities={}, state={},
        stores={}, logs=[], hardware_fingerprint=fingerprint,
    )["hardware_fingerprint"])

    for secret in ("PF4ABC123", "BS9XYZ987", "4c4c4544", "5CD1234XYZ", "SN12345678",
                   "aa:bb:cc:dd:ee:ff", "192.168.1.20", "Ana's DualSense", "edid",
                   "7QK2T93", "Ana's Keyboard", "/home/ana", "aa:bb:cc:dd:ee:01"):
        assert secret not in text
    assert fingerprint["dmi"] == {"sys_vendor": "LENOVO", "product_name": "83E1",
                                  "bios_version": "1.0.0.4"}
    surfaces = fingerprint["surfaces"]
    assert surfaces["drm"]["sys/class/drm/card1-eDP-1/modes"] == "1920x1200"
    assert surfaces["power_supply"][
        "sys/class/power_supply/BAT0/charge_control_end_threshold"] == "80"
    assert surfaces["power_supply"]["sys/class/power_supply/BAT0/model_name"] == "batt [mac]"
    assert {key: value for key, value in surfaces["power_supply"].items() if "hid-" in key} == {
        "sys/class/power_supply/hid-[mac]-battery/scope": "Device",
        "sys/class/power_supply/hid-[mac]-battery/scope#2": "Device",
    }
    assert surfaces["hwmon"] == {"sys/class/hwmon/hwmon0/name": "amdgpu",
                                 "sys/class/hwmon/hwmon1/name": "asus",
                                 "sys/class/hwmon/hwmon1/fan1_input": "3200"}
    fw = "sys/class/firmware-attributes/hp-bioscfg/attributes"
    assert surfaces["firmware_attributes"] == {
        f"{fw}/System Board CT Number/current_value": "[serial]",
        f"{fw}/ppt_pl1_spl/current_value": "15",
    }
    assert fingerprint["system"] == {"kernel": "6.11.0.1-bazzite", "distro": {"ID": "bazzite"}}
    assert fingerprint["panel"]["tdp"] == {"ryzenadj": "~/bin/ryzenadj", "note": "[user] at [ip]"}
    assert fingerprint["input_devices"] == [
        {"bus": "0003", "vendor": "17ef", "product": "6182", "version": "0111",
         "name": "Legion Controller", "handlers": "event5 js0"},
        {"bus": "0005", "vendor": "054c", "product": "0ce6", "version": "8100",
         "handlers": "event9"},
    ]


def test_a_failing_section_and_a_stalled_read_still_return_the_rest(tmp_path, monkeypatch):
    _machine(tmp_path)

    def broken(reader):
        raise PermissionError

    monkeypatch.setattr(hardware_fingerprint, "_cpu", broken)
    ticks = iter(range(10_000))

    fingerprint = hardware_fingerprint.collect(
        str(tmp_path), deadline_s=8, clock=lambda: next(ticks))

    assert fingerprint["errors"] == {"cpu": "PermissionError"}
    assert fingerprint["dmi"]["sys_vendor"] == "LENOVO"
    assert "deadline" in fingerprint["truncated"]


def test_fingerprint_is_bounded_and_names_what_it_dropped(tmp_path):
    _machine(tmp_path)
    for index in range(200):
        _write(tmp_path, f"sys/class/firmware-attributes/think-lmi/attributes/a{index}/"
               "possible_values", "x;" * 2000)

    fingerprint = hardware_fingerprint.collect(str(tmp_path), max_bytes=32 * 1024)

    assert len(json.dumps(fingerprint)) <= 32 * 1024
    assert fingerprint["truncated"] == ["surfaces/firmware_attributes"]
    assert fingerprint["dmi"]["product_name"] == "83E1"
