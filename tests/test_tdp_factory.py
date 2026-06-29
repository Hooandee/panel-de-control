import os

from device_profiles import DEVICE_TABLE, GENERIC
from tdp.factory import select_backend


def _p(key):
    return next(x for x in DEVICE_TABLE if x.key == key)


def _mk_fw(root, driver, pl1_max=35):
    base = os.path.join(root, "sys/class/firmware-attributes", driver, "attributes")
    for attr, mx in (("ppt_pl1_spl", pl1_max), ("ppt_pl2_sppt", 45), ("ppt_pl3_fppt", 55)):
        d = os.path.join(base, attr)
        os.makedirs(d, exist_ok=True)
        for f, v in (("current_value", 15), ("min_value", 5), ("max_value", mx)):
            with open(os.path.join(d, f), "w") as fh:
                fh.write(str(v))


def _mk_hwmon(root):
    d = os.path.join(root, "sys/class/hwmon/hwmon0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write("steamdeck_hwmon")
    with open(os.path.join(d, "power1_cap"), "w") as f:
        f.write("15000000")


_NO_RYZENADJ = lambda: None  # noqa: E731


def test_rog_uses_asus_armoury_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury")
    b = select_backend(_p("rog_xbox_ally_x"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "asus-armoury" in b.name


def test_legion_uses_lenovo_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    b = select_backend(_p("legion_go_2"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "lenovo-wmi-other" in b.name


def test_msi_uses_msi_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "msi-wmi-platform")
    b = select_backend(_p("msi_claw_8_ai_plus"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "msi-wmi-platform" in b.name


def test_steam_deck_uses_hwmon(tmp_path):
    root = str(tmp_path)
    _mk_hwmon(root)
    b = select_backend(_p("steam_deck_oled"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and b.name == "steamdeck-hwmon"


def test_falls_back_to_null_when_nothing_present(tmp_path):
    b = select_backend(_p("rog_ally_x"), root=str(tmp_path), ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported is False and b.name == "unsupported"


def test_generic_amd_uses_ryzenadj_when_present(tmp_path):
    b = select_backend(GENERIC, root=str(tmp_path), ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and b.name == "ryzenadj"
