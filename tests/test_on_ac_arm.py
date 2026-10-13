import os

from lifecycle import read_on_ac


def _supply(root, name, kind, online):
    d = os.path.join(root, "sys/class/power_supply", name)
    os.makedirs(d)
    with open(os.path.join(d, "type"), "w") as handle:
        handle.write(kind)
    if online is not None:
        with open(os.path.join(d, "online"), "w") as handle:
            handle.write(online)


def test_usb_charger_counts_when_the_machine_has_no_mains_supply(tmp_path):
    root = str(tmp_path)
    _supply(root, "battery", "Battery", None)
    _supply(root, "qcom-battmgr-usb", "USB", "1")
    assert read_on_ac(root) is True


def test_unplugged_usb_without_mains_is_battery(tmp_path):
    root = str(tmp_path)
    _supply(root, "battery", "Battery", None)
    _supply(root, "qcom-battmgr-usb", "USB", "0")
    _supply(root, "qcom-battmgr-wls", "Wireless", "0")
    assert read_on_ac(root) is False


def test_mains_stays_authoritative_over_an_online_usb_port(tmp_path):
    root = str(tmp_path)
    _supply(root, "ACAD", "Mains", "0")
    _supply(root, "ucsi-source-psy-USBC000:001", "USB", "1")
    assert read_on_ac(root) is False
