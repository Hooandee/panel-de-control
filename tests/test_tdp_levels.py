import os
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.backend import NullBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)


def _mk(root, driver="asus-armoury"):
    base = os.path.join(root, "sys/class/firmware-attributes", driver, "attributes")
    for attr, mn, mx in (("ppt_pl1_spl", 7, 35), ("ppt_pl2_sppt", 13, 45), ("ppt_pl3_fppt", 19, 55)):
        d = os.path.join(base, attr)
        os.makedirs(d, exist_ok=True)
        for f, v in (("current_value", 20), ("min_value", mn), ("max_value", mx)):
            with open(os.path.join(d, f), "w") as fh:
                fh.write(str(v))
    return base


def test_supports_levels_flag():
    assert NullBackend("x").supports_levels is False


def test_firmware_attr_supports_levels(tmp_path):
    _mk(str(tmp_path))
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=str(tmp_path))
    assert b.supports_levels is True


def test_level_limits_reads_each_pl(tmp_path):
    _mk(str(tmp_path))
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=str(tmp_path))
    ll = b.level_limits()
    assert ll["pl1"] == {"min": 7, "max": 35}
    assert ll["pl2"] == {"min": 13, "max": 45}
    assert ll["pl3"] == {"min": 19, "max": 55}


def test_set_levels_writes_each_clamped_pl1_last(tmp_path):
    root = str(tmp_path)
    base = _mk(root)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    res = b.set_levels(30, 99, 1, ac=True)  # pl2 over max→45, pl3 under min→19
    assert res.ok is True and res.applied_w == 30

    def rd(a):
        return open(os.path.join(base, a, "current_value")).read().strip()

    assert rd("ppt_pl1_spl") == "30"
    assert rd("ppt_pl2_sppt") == "45"
    assert rd("ppt_pl3_fppt") == "19"


def test_set_tdp_still_works_and_derives_boost(tmp_path):
    root = str(tmp_path)
    base = _mk(root)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    res = b.set_tdp(20, ac=True)
    assert res.ok and res.applied_w == 20
    assert open(os.path.join(base, "ppt_pl1_spl", "current_value")).read().strip() == "20"
    # pl2/pl3 derived above pl1 (>=20), clamped to their maxima
    assert int(open(os.path.join(base, "ppt_pl2_sppt", "current_value")).read()) >= 20
    assert int(open(os.path.join(base, "ppt_pl3_fppt", "current_value")).read()) >= 20


def test_null_set_levels_degrades():
    b = NullBackend("x")
    assert b.set_levels(15, 15, 15, ac=True).ok is False
