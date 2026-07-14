import os

import pytest

from device_registry import detect
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=4, default_w=15, max_w=30, max_ac_w=30)

# Real firmware ppt maxes (pl1, sppt, fppt) probed on hardware. The sanitizer must
# TRUST these — never cap a healthy device below its real limits. Guards against a
# profile's charger max being lowered under a device's real firmware ceiling.
_REAL_FW_MAXES = {
    "ROG Xbox Ally X RC73XA_RC73XA": (35, 45, 55),
    "ROG Ally X RC72LA_RC72LA": (30, 43, 53),
    "83N0": (35, 37, 45),  # Legion Go 2
}


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


def _mk_profile(root, name="lenovo-wmi-gamezone", cur="balanced",
                choices="low-power balanced performance custom"):
    d = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(name)
    with open(os.path.join(d, "profile"), "w") as f:
        f.write(cur)
    if choices is not None:
        with open(os.path.join(d, "choices"), "w") as f:
            f.write(choices)
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


def _legion(root):
    _mk_full(root)
    _mk_profile(root, cur="performance")
    return FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root,
                               profile_name="lenovo-wmi-gamezone")


def test_read_profile(tmp_path):
    b = _legion(str(tmp_path))
    assert b.read_profile() == "performance"


def test_profile_choices(tmp_path):
    b = _legion(str(tmp_path))
    assert b.profile_choices() == ["low-power", "balanced", "performance", "custom"]


def test_set_profile_writes_and_confirms(tmp_path):
    root = str(tmp_path)
    b = _legion(root)
    assert b.set_profile("low-power") is True
    assert b.read_profile() == "low-power"


def test_set_profile_rejects_unknown_mode(tmp_path):
    root = str(tmp_path)
    b = _legion(root)
    assert b.set_profile("turbo") is False
    assert b.read_profile() == "performance"  # unchanged


def test_profile_helpers_none_without_profile_name(tmp_path):
    root = str(tmp_path)
    _mk_full(root)
    _mk_profile(root)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root)  # no profile_name
    assert b.read_profile() is None
    assert b.profile_choices() == []
    assert b.set_profile("balanced") is False


def _mk_pl1(root, driver, cur, mn, mx):
    _mk_attr(root, driver, "ppt_pl1_spl", cur, mn, mx)


def test_bogus_firmware_pl1_max_is_capped_for_recognised_device(tmp_path):
    # A broken BIOS reporting 150 W must not expose a 150 W slider — fall back to
    # the profile charger ceiling (30).
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 7, 150)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    assert b.get_limits().max_ac_w == 30


def test_firmware_pl1_max_within_margin_is_trusted(tmp_path):
    # Slightly above the profile charger max (30) but plausible → trust the firmware.
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 7, 38)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    assert b.get_limits().max_ac_w == 38


def test_rog_xbox_ally_z2a_bogus_100w_capped_to_profile(tmp_path):
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 15, 5, 100)
    fallback = TdpLimits.from_profile(detect(product_name="ROG Xbox Ally RC73YA_RC73YA"))
    lim = FirmwareAttrBackend("asus-armoury", fallback, root=root).get_limits()
    assert lim.max_ac_w == 20
    assert lim.max_w == 17


def test_generic_device_only_rejects_absurd_pl1_max(tmp_path):
    # No trustworthy reference on an unrecognised device: a high-but-possible value
    # is trusted; a physically-impossible one is dropped to the absurd bound.
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 7, 50)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root, is_generic=True)
    assert b.get_limits().max_ac_w == 50
    root2 = str(tmp_path / "b")
    _mk_pl1(root2, "asus-armoury", 20, 7, 150)
    b2 = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root2, is_generic=True)
    assert b2.get_limits().max_ac_w == 100


def test_generic_device_battery_max_trusts_firmware(tmp_path):
    # A generic (unrecognised) device's profile max_w is only a placeholder (15 W).
    # On battery, trust the firmware's real sustained ceiling instead of capping there
    # — else a capable handheld is stuck far below what its firmware allows.
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 5, 30)
    generic_fb = TdpLimits(min_w=4, default_w=10, max_w=15, max_ac_w=15)
    b = FirmwareAttrBackend("asus-armoury", generic_fb, root=root, is_generic=True)
    lim = b.get_limits()
    assert lim.max_w == 30
    assert lim.max_ac_w == 30


def test_recognised_device_keeps_battery_policy_below_firmware(tmp_path):
    # A recognised device keeps its intentional on-battery policy even when the
    # firmware ceiling is higher (charger-only boost stays a charger-only boost).
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 5, 35)
    fb = TdpLimits(min_w=5, default_w=15, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)  # is_generic=False
    lim = b.get_limits()
    assert lim.max_w == 25       # battery policy preserved
    assert lim.max_ac_w == 35    # firmware ceiling on charger


def test_bogus_firmware_all_rails_fall_back_to_profile(tmp_path):
    # Some ASUS kernels report every ppt rail max as 150 W on the Xbox Ally X. With a
    # recognised profile (charger max 35) the whole set is distrusted: PL1 -> 35 and the
    # boost rails -> profile-scaled, so neither the slider nor Advanced exposes 150.
    root = str(tmp_path)
    for attr in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        _mk_attr(root, "asus-armoury", attr, 7, 5, 150)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    assert b.get_limits().max_ac_w == 35
    ll = b.level_limits()
    assert ll["pl1"]["max"] == 35
    assert ll["pl2"]["max"] == round(35 * 1.2)  # 42
    assert ll["pl3"]["max"] == round(35 * 1.4)  # 49


def test_trustworthy_firmware_keeps_real_boost_maxes(tmp_path):
    # A healthy firmware (PL1 within margin) keeps its real per-rail maxes, so genuine
    # SPPT/FPPT boost above PL1 is preserved.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 17, 7, 35)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 25, 13, 45)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 33, 19, 55)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    ll = b.level_limits()
    assert (ll["pl1"]["max"], ll["pl2"]["max"], ll["pl3"]["max"]) == (35, 45, 55)


@pytest.mark.parametrize("product,maxes", _REAL_FW_MAXES.items())
def test_real_firmware_maxes_are_trusted(tmp_path, product, maxes):
    dev = detect(product_name=product)
    driver = "asus-armoury" if product.startswith("ROG") else "lenovo-wmi-other"
    root = str(tmp_path)
    pl1, sppt, fppt = maxes
    _mk_attr(root, driver, "ppt_pl1_spl", 15, 5, pl1)
    _mk_attr(root, driver, "ppt_pl2_sppt", 15, 5, sppt)
    _mk_attr(root, driver, "ppt_pl3_fppt", 15, 5, fppt)
    b = FirmwareAttrBackend(driver, TdpLimits.from_profile(dev), root=root,
                            is_generic=dev.is_generic)
    ll = b.level_limits()
    assert (ll["pl1"]["max"], ll["pl2"]["max"], ll["pl3"]["max"]) == (pl1, sppt, fppt)
    assert b.get_limits().max_ac_w == pl1
