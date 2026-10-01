import os

from report import collector, connected_devices


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(value + "\n")


def _driver(root, device_path, driver):
    target = os.path.join(root, "sys/bus/drivers", driver)
    os.makedirs(target, exist_ok=True)
    os.symlink(target, os.path.join(device_path, "driver"))


def _usb_device(root, name, vendor, product, label, serial="AB12CD34EF56"):
    path = os.path.join(root, "sys/bus/usb/devices", name)
    for leaf, value in (("idVendor", vendor), ("idProduct", product),
                        ("product", label), ("speed", "480"), ("serial", serial)):
        _write(os.path.join(path, leaf), value)
    return path


def test_usb_devices_list_ids_names_and_interface_drivers_without_serial(tmp_path):
    root = str(tmp_path)
    _usb_device(root, "3-1", "2f24", "0137", "Frost Bay")
    interface = os.path.join(root, "sys/bus/usb/devices/3-1:1.0")
    _write(os.path.join(interface, "bInterfaceClass"), "03")
    _driver(root, interface, "usbhid")

    usb = connected_devices.snapshot(root)["usb"]

    assert usb == [{
        "bus_path": "3-1", "idVendor": "2f24", "idProduct": "0137",
        "product": "Frost Bay", "speed": "480",
        "interfaces": [{"bInterfaceClass": "03", "driver": "usbhid"}],
    }]


def test_usb_interfaces_do_not_consume_the_device_cap(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(connected_devices, "_MAX_PER_BUS", 1)
    for index in range(3):
        _write(os.path.join(root, f"sys/bus/usb/devices/1-0:1.{index}", "bInterfaceClass"), "09")
    _usb_device(root, "1-1", "045e", "028e", "Controller")

    assert [d["bus_path"] for d in connected_devices.snapshot(root)["usb"]] == ["1-1"]


def test_input_devices_never_read_phys_or_uniq(tmp_path):
    root = str(tmp_path)
    path = os.path.join(root, "sys/class/input/input7")
    _write(os.path.join(path, "name"), "Xbox Wireless Controller")
    _write(os.path.join(path, "uniq"), "aa:bb:cc:dd:ee:ff")
    _write(os.path.join(path, "phys"), "aa:bb:cc:dd:ee:00")
    _write(os.path.join(path, "id/bustype"), "0003")
    _write(os.path.join(path, "id/vendor"), "045e")
    _write(os.path.join(path, "id/product"), "0b12")

    assert connected_devices.snapshot(root)["input"] == [{
        "name": "Xbox Wireless Controller",
        "id_bustype": "0003", "id_vendor": "045e", "id_product": "0b12",
    }]


def test_pci_hid_thunderbolt_and_bluetooth_adapters(tmp_path):
    root = str(tmp_path)
    pci = os.path.join(root, "sys/bus/pci/devices/0000:c5:00.0")
    for leaf, value in (("vendor", "0x1002"), ("device", "0x1586"), ("class", "0x030000")):
        _write(os.path.join(pci, leaf), value)
    _driver(root, pci, "amdgpu")
    hid = os.path.join(root, "sys/bus/hid/devices/0003:045E:028E.0001")
    os.makedirs(hid)
    _driver(root, hid, "hid-generic")
    tb = os.path.join(root, "sys/bus/thunderbolt/devices/0-1")
    _write(os.path.join(tb, "vendor_name"), "Razer")
    _write(os.path.join(tb, "device_name"), "Core X")
    os.makedirs(os.path.join(root, "sys/class/bluetooth/hci0"))
    os.makedirs(os.path.join(root, "sys/class/bluetooth/hci0:256"))

    snap = connected_devices.snapshot(root)

    assert snap["pci"] == [{"address": "0000:c5:00.0", "vendor": "1002",
                            "device": "1586", "class": "030000", "driver": "amdgpu"}]
    assert snap["hid"] == [{"id": "0003:045E:028E.0001", "driver": "hid-generic"}]
    assert snap["thunderbolt"] == [{"id": "0-1", "vendor_name": "Razer", "device_name": "Core X"}]
    assert snap["bluetooth_adapters"] == [{"id": "hci0"}]


def test_missing_buses_are_empty_lists(tmp_path):
    assert connected_devices.snapshot(str(tmp_path)) == {
        "usb": [], "hid": [], "input": [], "pci": [], "thunderbolt": [],
        "bluetooth_adapters": [],
    }


def test_sysfs_snapshot_carries_connected_devices_redacted(tmp_path):
    root = str(tmp_path)
    _usb_device(root, "3-1", "2f24", "0137", "Frost Bay", serial="SN9X8Y7Z6W5V")

    snap = collector.sysfs_snapshot(root)

    assert snap["connected_devices"]["usb"][0]["product"] == "Frost Bay"
    assert "SN9X8Y7Z6W5V" not in str(snap)


def _input_device(root, name, label, bustype):
    path = os.path.join(root, "sys/class/input", name)
    _write(os.path.join(path, "name"), label)
    _write(os.path.join(path, "id/bustype"), bustype)
    _write(os.path.join(path, "id/vendor"), "0000")
    _write(os.path.join(path, "id/product"), "0000")


def test_bluetooth_input_names_are_dropped(tmp_path):
    root = str(tmp_path)
    _input_device(root, "input1", "Juan's Pad", "0005")
    _input_device(root, "input2", "Juan's AirPods Pro (AVRCP)", "0006")

    names = [d.get("name") for d in connected_devices.snapshot(root)["input"]]
    assert names == [None, None]


def test_root_hub_lists_its_interfaces(tmp_path):
    root = str(tmp_path)
    _usb_device(root, "usb1", "1d6b", "0002", "xHCI Host Controller")
    interface = os.path.join(root, "sys/bus/usb/devices/1-0:1.0")
    _write(os.path.join(interface, "bInterfaceClass"), "09")
    _driver(root, interface, "hub")

    usb = connected_devices.snapshot(root)["usb"]
    assert usb[0]["interfaces"] == [{"bInterfaceClass": "09", "driver": "hub"}]


def test_bus_over_the_cap_reports_its_real_count(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(connected_devices, "_MAX_PER_BUS", 2)
    for index in range(3):
        os.makedirs(os.path.join(root, f"sys/bus/hid/devices/0003:0000:000{index}.0001"))

    snap = connected_devices.snapshot(root)
    assert len(snap["hid"]) == 2
    assert snap["truncated"] == {"hid": 3}


def test_pci_class_survives_report_redaction(tmp_path):
    root = str(tmp_path)
    pci = os.path.join(root, "sys/bus/pci/devices/0000:c5:00.0")
    for leaf, value in (("vendor", "0x1002"), ("device", "0x1586"), ("class", "0x030000")):
        _write(os.path.join(pci, leaf), value)

    snap = collector.sysfs_snapshot(root)
    assert snap["connected_devices"]["pci"][0]["class"] == "030000"
