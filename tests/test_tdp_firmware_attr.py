import os

from tdp.firmware_attr import FirmwareAttrBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=4, default_w=15, max_w=30, max_ac_w=30)


def _mk_attr(root, driver, attr, cur, mn, mx):
    d = os.path.join(root, "sys/class/firmware-attributes", driver, "attributes", attr)
    os.makedirs(d, exist_ok=True)
    for f, v in (("current_value", cur), ("min_value", mn), ("max_value", mx)):
        with open(os.path.join(d, f), "w") as fh:
            fh.write(str(v))


def _mk_full(root, driver="lenovo-wmi-other-0"):
    _mk_attr(root, driver, "ppt_pl1_spl", 35, 5, 35)
    _mk_attr(root, driver, "ppt_pl2_sppt", 37, 5, 37)
    _mk_attr(root, driver, "ppt_pl3_fppt", 45, 5, 45)


def _mk_profile(root, name="lenovo-wmi-gamezone", cur="balanced"):
    d = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(name)
    with open(os.path.join(d, "profile"), "w") as f:
        f.write(cur)
    return os.path.join(d, "profile")


def test_unsupported_when_absent(tmp_path):
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=str(tmp_path))
    assert b.supported is False


def test_matches_driver_by_prefix(tmp_path):
    _mk_full(str(tmp_path), "lenovo-wmi-other-0")
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=str(tmp_path))
    assert b.supported is True


def test_get_limits_reads_sysfs_bounds(tmp_path):
    _mk_full(str(tmp_path))
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=str(tmp_path))
    lim = b.get_limits()
    assert lim.min_w == 5
    assert lim.max_w == 30   # battery = device policy (fallback.max_w)
    assert lim.max_ac_w == 35  # charger = firmware sysfs max
    assert lim.default_w == 15  # fallback default, clamped into [5,35]


def test_set_tdp_writes_pl1_and_reads_back(tmp_path):
    root = str(tmp_path)
    _mk_full(root)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root)
    res = b.set_tdp(25, ac=True)
    assert res.ok is True and res.applied_w == 25
    spl = open(os.path.join(root, "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/ppt_pl1_spl/current_value")).read().strip()
    assert spl == "25"
    assert b.read_applied() == 25


def test_set_tdp_clamps_to_sysfs_max(tmp_path):
    root = str(tmp_path)
    _mk_full(root)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root)
    res = b.set_tdp(999, ac=True)
    assert res.applied_w == 35  # clamped to pl1 max


def test_lenovo_profile_prestep_sets_custom(tmp_path):
    root = str(tmp_path)
    _mk_full(root)
    prof = _mk_profile(root)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root, profile_name="lenovo-wmi-gamezone")
    b.set_tdp(20, ac=True)
    assert open(prof).read().strip() == "custom"
