import os
import inspect

from device_registry import detect
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.types import RailReading, TdpLimits, TdpObservation

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


def _settling_backend(root, *delays):
    _mk_full(root)
    return FirmwareAttrBackend(
        "lenovo-wmi-other",
        FALLBACK,
        root=root,
        readback_settle_delays=delays,
    )


def _observation(backend, pl1, pl2, pl3):
    return TdpObservation(
        readable=True,
        surfaces={
            backend.name: {
                "pl1": RailReading(pl1),
                "pl2": RailReading(pl2),
                "pl3": RailReading(pl3),
            },
        },
    )


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


def test_recognised_get_limits_is_the_profile_not_firmware(tmp_path):
    # A recognised device's slider range comes from its PROFILE, never the firmware's
    # reported max — that value lies (low on battery / momentarily) and, cached, froze
    # users below the real limit. Firmware says 35 here; the profile (30) still wins.
    _mk_full(str(tmp_path))  # firmware pl1 max = 35
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=str(tmp_path))
    lim = b.get_limits()
    assert (lim.min_w, lim.default_w, lim.max_w, lim.max_ac_w) == (4, 15, 30, 30)


def test_recognised_get_limits_ignores_a_low_firmware_read(tmp_path):
    # The whole point: firmware momentarily reports a low max (15). The profile still
    # gives the full range — no more "stuck at 15 W".
    _mk_attr(str(tmp_path), "lenovo-wmi-other-0", "ppt_pl1_spl", 13, 5, 15)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=str(tmp_path))
    assert b.get_limits().max_ac_w == 30  # profile, not the bogus 15


def test_set_tdp_writes_pl1_and_reads_back(tmp_path):
    root = str(tmp_path)
    _mk_full(root)
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root)
    res = b.set_tdp(25, ac=True)
    assert res.ok is True and res.applied_w == 25
    spl = open(os.path.join(root, "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/ppt_pl1_spl/current_value")).read().strip()
    assert spl == "25"
    assert b.read_applied() == 25


def test_set_levels_rechecks_async_readback_without_rewriting(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    b = _settling_backend(root, 0)
    stale = _observation(b, 35, 37, 45)
    original_observe = b.observe
    observations = iter((stale,))

    def observe_after_firmware_settles():
        return next(observations, None) or original_observe()

    writes = []
    original_write = b._write

    def record_write(path, value):
        writes.append((path, value))
        return original_write(path, value)

    monkeypatch.setattr(b, "observe", observe_after_firmware_settles)
    monkeypatch.setattr(b, "_write", record_write)

    result = b.set_levels(20, 20, 20, ac=True)

    assert result.ok is True
    assert result.applied_w == 20
    assert [
        value
        for path, value in writes
        if path.endswith("current_value")
    ] == [20, 20, 20]


def test_set_levels_keeps_failure_when_async_readback_never_converges(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    b = _settling_backend(root, 0, 0)
    stale = _observation(b, 35, 37, 45)
    monkeypatch.setattr(b, "observe", lambda: stale)

    result = b.set_levels(20, 20, 20, ac=True)

    assert result.ok is False
    assert result.applied_w == 35
    assert f"{b.name}/pl1=35" in result.detail


def test_set_levels_never_succeeds_when_primary_readback_disappears(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    b = _settling_backend(root, 0)
    unavailable = TdpObservation(readable=False)
    monkeypatch.setattr(b, "observe", lambda: unavailable)

    result = b.set_levels(20, 20, 20, ac=True)

    assert result.ok is False
    assert result.applied_w is None
    assert f"{b.name}/pl1=unavailable" in result.detail


def test_set_levels_never_succeeds_when_primary_sysfs_disappears_after_probe(
    tmp_path,
):
    root = str(tmp_path)
    b = _settling_backend(root, 0)
    for attr in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        os.remove(b._attr(attr))

    result = b.set_levels(20, 20, 20, ac=True)

    assert result.ok is False
    assert result.applied_w is None
    assert f"{b.name}/pl1=unavailable" in result.detail


def test_set_levels_does_not_wait_after_a_write_error(tmp_path, monkeypatch):
    root = str(tmp_path)
    b = _settling_backend(root, 0)
    original_write = b._write
    pl2_path = b._attr("ppt_pl2_sppt")

    def reject_pl2(path, value):
        return False if path == pl2_path else original_write(path, value)

    observations = 0
    original_observe = b.observe

    def count_observations():
        nonlocal observations
        observations += 1
        return original_observe()

    monkeypatch.setattr(b, "_write", reject_pl2)
    monkeypatch.setattr(b, "observe", count_observations)

    result = b.set_levels(20, 20, 20, ac=True)

    assert result.ok is False
    assert observations == 1
    assert f"{b.name}/pl2" in result.detail


def test_set_tdp_clamps_to_profile_then_live_firmware(tmp_path):
    # Requested 999 → capped to the profile charger max (30), then the write clamps to
    # the live firmware ceiling (35 here, so 30 stands).
    root = str(tmp_path)
    _mk_full(root)  # firmware pl1 max = 35
    b = FirmwareAttrBackend("lenovo-wmi-other", FALLBACK, root=root)
    assert b.set_tdp(999, ac=True).applied_w == 30


def test_write_clamps_to_live_firmware_ceiling(tmp_path):
    # The firmware only accepts 25 right now (Ally on battery). Even asking 30 (within
    # the profile), the write clamps to the live ceiling and honestly applies 25 —
    # writing above it would be rejected/penalised by the firmware.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 13, 7, 25)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 13, 7, 30)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 13, 7, 35)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=30)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    res = b.set_tdp(30, ac=True)
    assert res.ok is True and res.applied_w == 25


def test_bounds_are_read_live_not_cached(tmp_path):
    # The core fix: the firmware ceiling is re-read on every write, so an Ally that
    # rises from 25 (battery) to 30 (charger) reaches 30 without reloading the plugin.
    root = str(tmp_path)
    d = os.path.join(root, "sys/class/firmware-attributes/asus-armoury/attributes/ppt_pl1_spl")
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 13, 7, 25)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 13, 7, 43)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 13, 7, 53)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=30)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    assert b.set_tdp(30, ac=True).applied_w == 25   # battery ceiling
    with open(os.path.join(d, "max_value"), "w") as f:
        f.write("30")                               # charger plugged
    assert b.set_tdp(30, ac=True).applied_w == 30   # picked up live, no reload


def test_write_never_exceeds_profile_ceiling_when_firmware_lies(tmp_path):
    # Safety invariant: a recognised device's WRITE clamp must bound to the profile
    # ceiling, not the firmware's live max. The Xbox Ally X firmware reports a bogus
    # ppt max of 150 W; a write must still land at the 35 W profile charger max — never
    # cook a 35 W handheld at 150 W, whatever value reaches set_levels.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 35, 5, 150)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 42, 5, 150)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 49, 5, 150)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    # Even asked for the bogus 150 directly on every rail, each rail clamps to its
    # profile-derived ceiling (PL1 35, SPPT 42, FPPT 49).
    res = b.set_levels(150, 150, 150, ac=True)
    assert res.applied_w == 35
    p = os.path.join(root, "sys/class/firmware-attributes/asus-armoury/attributes")
    assert open(os.path.join(p, "ppt_pl2_sppt/current_value")).read().strip() == "42"
    assert open(os.path.join(p, "ppt_pl3_fppt/current_value")).read().strip() == "49"


def test_write_still_honours_a_low_live_firmware_ceiling(tmp_path):
    # The profile cap must not defeat the dynamic battery/charger behaviour: when the
    # firmware genuinely reports a LOWER live max (25 on battery) the write clamps to
    # min(firmware, profile) = 25, not the profile's 35.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 13, 7, 25)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 13, 7, 30)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 13, 7, 35)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    assert b.set_levels(35, 42, 49, ac=True).applied_w == 25


def _mk_legacy(root, pl1="20", pl2="24", fppt="28"):
    # The ASUS legacy interface (asus-nb-wmi): direct ppt files, not the current_value/
    # min_value/max_value triplet. This is the second PL1 interface Steam/HHD write.
    d = os.path.join(root, "sys/devices/platform/asus-nb-wmi")
    os.makedirs(d, exist_ok=True)
    for f, v in (("ppt_pl1_spl", pl1), ("ppt_pl2_sppt", pl2), ("ppt_fppt", fppt)):
        with open(os.path.join(d, f), "w") as fh:
            fh.write(v)
    return d


def test_writes_both_pl1_interfaces_when_legacy_present(tmp_path):
    # On an ASUS device with the dual PL1 interface, a write must also assert the legacy
    # asus-nb-wmi nodes so our setpoint is the last writer and Steam/HHD/firmware can't
    # silently hold the effective PL1 higher. Firmware max lies (150) → both interfaces
    # land at the profile ceiling (PL1 35, SPPT 42, FPPT 49), never 150.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 35, 5, 150)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 42, 5, 150)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 49, 5, 150)
    legacy = _mk_legacy(root)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    b.set_levels(150, 150, 150, ac=True)
    assert open(os.path.join(legacy, "ppt_pl1_spl")).read().strip() == "35"
    assert open(os.path.join(legacy, "ppt_pl2_sppt")).read().strip() == "42"
    assert open(os.path.join(legacy, "ppt_fppt")).read().strip() == "49"


def test_legacy_interface_absent_is_a_clean_noop(tmp_path):
    # No asus-nb-wmi (non-ASUS, or a kernel that dropped the legacy ppt nodes): the write
    # still succeeds via the firmware-attributes path, no error.
    root = str(tmp_path)
    _mk_full(root, "asus-armoury")
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    res = b.set_levels(20, 24, 28, ac=True)
    assert res.ok is True and res.applied_w == 20


def test_legacy_only_boost_rails_do_not_require_primary_readback(tmp_path):
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 20, 7, 35)
    _mk_legacy(root, pl1="20", pl2="24", fppt="28")
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)

    result = b.set_levels(20, 24, 28, ac=True)

    assert result.ok is True
    assert result.applied_w == 20


def test_set_levels_fails_if_legacy_readback_disappears_after_write(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _mk_full(root, "asus-armoury")
    _mk_legacy(root)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    original_observe = b.observe

    def observe_after_legacy_disappears():
        os.remove(b._legacy["pl2"])
        return original_observe()

    monkeypatch.setattr(b, "observe", observe_after_legacy_disappears)

    result = b.set_levels(20, 24, 28, ac=True)

    assert result.ok is False
    assert "asus-nb-wmi/pl2=unavailable" in result.detail


def test_observe_reads_every_primary_rail_and_live_bound(tmp_path):
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 10, 7, 30)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 15, 15, 43)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 15, 15, 53)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    obs = b.observe()
    rails = obs.surfaces["firmware-attr:asus-armoury"]
    assert rails["pl1"].as_dict() == {
        "applied": 10,
        "min": 7,
        "max": 30,
    }
    assert rails["pl2"].as_dict() == {
        "applied": 15,
        "min": 15,
        "max": 43,
    }
    assert rails["pl3"].as_dict() == {
        "applied": 15,
        "min": 15,
        "max": 53,
    }


def test_observe_includes_asus_legacy_surface(tmp_path):
    root = str(tmp_path)
    _mk_full(root, "asus-armoury")
    _mk_legacy(root, pl1="30", pl2="35", fppt="40")
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    legacy = b.observe().surfaces["asus-nb-wmi"]
    assert {rail: value.applied_w for rail, value in legacy.items()} == {
        "pl1": 30,
        "pl2": 35,
        "pl3": 40,
    }


def test_set_levels_fails_if_one_legacy_rail_does_not_stick(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _mk_full(root, "asus-armoury")
    legacy = _mk_legacy(root)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root)
    original_write = b._write

    def reject_legacy_pl2(path, value):
        if path == os.path.join(legacy, "ppt_pl2_sppt"):
            return False
        return original_write(path, value)

    monkeypatch.setattr(b, "_write", reject_legacy_pl2)
    res = b.set_levels(20, 24, 28, ac=True)
    assert res.ok is False
    assert "asus-nb-wmi/pl2" in res.detail


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


def test_rog_xbox_ally_z2a_bogus_100w_capped_to_profile(tmp_path):
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 15, 5, 100)
    fallback = TdpLimits.from_profile(detect(product_name="ROG Xbox Ally RC73YA_RC73YA"))
    lim = FirmwareAttrBackend("asus-armoury", fallback, root=root).get_limits()
    assert lim.max_ac_w == 20
    assert lim.max_w == 17


def test_generic_device_never_expands_conservative_pl1_max(tmp_path):
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 7, 50)
    b = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root, is_generic=True)
    assert b.get_limits().max_ac_w == FALLBACK.max_ac_w
    root2 = str(tmp_path / "b")
    _mk_pl1(root2, "asus-armoury", 20, 7, 150)
    b2 = FirmwareAttrBackend("asus-armoury", FALLBACK, root=root2, is_generic=True)
    assert b2.get_limits().max_ac_w == FALLBACK.max_ac_w


def test_generic_device_keeps_conservative_battery_max(tmp_path):
    root = str(tmp_path)
    _mk_pl1(root, "asus-armoury", 20, 5, 30)
    generic_fb = TdpLimits(min_w=4, default_w=10, max_w=15, max_ac_w=15)
    b = FirmwareAttrBackend("asus-armoury", generic_fb, root=root, is_generic=True)
    lim = b.get_limits()
    assert lim.max_w == 15
    assert lim.max_ac_w == 15


def test_contradictory_live_min_never_overrides_safe_ceiling(tmp_path):
    root = str(tmp_path)
    for attr in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        _mk_attr(root, "asus-armoury", attr, 80, 80, 150)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    b = FirmwareAttrBackend("asus-armoury", fb, root=root)
    result = b.set_levels(35, 42, 49, ac=True)
    assert result.ok is True
    assert result.applied_w == 35


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


def test_recognised_level_limits_are_profile_derived(tmp_path):
    # Recognised device: the Advanced rails come from the profile (PL1 = charger max,
    # SPPT ×1.2, FPPT ×1.4), NOT the firmware's reported maxes — same reason as the
    # slider. Firmware here reports 45/55; the profile (charger 35) still drives it.
    root = str(tmp_path)
    _mk_attr(root, "asus-armoury", "ppt_pl1_spl", 17, 7, 35)
    _mk_attr(root, "asus-armoury", "ppt_pl2_sppt", 25, 13, 45)
    _mk_attr(root, "asus-armoury", "ppt_pl3_fppt", 33, 19, 55)
    fb = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)
    ll = FirmwareAttrBackend("asus-armoury", fb, root=root).level_limits()
    assert (ll["pl1"]["max"], ll["pl2"]["max"], ll["pl3"]["max"]) == (35, 42, 49)


def test_legion_go_s_reaches_profile_range_despite_low_firmware(tmp_path):
    # Firmware may under-report; the profile (charger 40) drives the slider + rails.
    root = str(tmp_path)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl1_spl", 13, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl2_sppt", 14, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl3_fppt", 15, 5, 20)
    fb = TdpLimits.from_profile(detect(product_name="83L3"))  # Legion Go S 5,15,33,40
    b = FirmwareAttrBackend("lenovo-wmi-other", fb, root=root,
                            profile_name="lenovo-wmi-gamezone")
    assert b.get_limits().max_ac_w == 40
    ll = b.level_limits()
    assert (ll["pl1"]["max"], ll["pl2"]["max"], ll["pl3"]["max"]) == (40, 48, 56)


def test_lenovo_write_clamps_to_live_firmware_when_low(tmp_path):
    # Firmware accepts only 15 now: the slider stays 40 but the write applies 15;
    # when it recovers to 33 the same set reaches 30 (live re-read).
    root = str(tmp_path)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl1_spl", 13, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl2_sppt", 14, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl3_fppt", 15, 5, 20)
    _mk_profile(root)
    fb = TdpLimits.from_profile(detect(product_name="83L3"))
    b = FirmwareAttrBackend("lenovo-wmi-other", fb, root=root,
                            profile_name="lenovo-wmi-gamezone")
    assert b.set_tdp(30, ac=True).applied_w == 15   # clamped to live, honest
    p1 = os.path.join(root, "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/ppt_pl1_spl")
    with open(os.path.join(p1, "max_value"), "w") as f:
        f.write("33")                               # firmware recovered
    assert b.set_tdp(30, ac=True).applied_w == 30   # now reaches the setpoint


def test_measured_rail_floors_turn_flat_15w_into_confirmed_15_15_20(tmp_path):
    assert "rail_floors" in inspect.signature(FirmwareAttrBackend).parameters
    root = str(tmp_path)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl1_spl", 30, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl2_sppt", 15, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl3_fppt", 20, 5, 20)
    _mk_profile(root)
    fb = TdpLimits.from_profile(detect(product_name="83N6"))
    b = FirmwareAttrBackend(
        "lenovo-wmi-other",
        fb,
        root=root,
        profile_name="lenovo-wmi-gamezone",
        rail_floors={"pl2": 15, "pl3": 20},
    )

    assert b.level_limits()["pl2"]["min"] == 15
    assert b.level_limits()["pl3"]["min"] == 20
    result = b.set_tdp(15, ac=True)
    assert result.ok is True
    assert result.applied_w == 15
    rails = b.observe().surfaces[b.name]
    assert {rail: reading.applied_w for rail, reading in rails.items()} == {
        "pl1": 15,
        "pl2": 15,
        "pl3": 20,
    }


def test_invalid_rail_floors_are_ignored_without_breaking_backend_init(tmp_path):
    _mk_full(str(tmp_path))

    backend = FirmwareAttrBackend(
        "lenovo-wmi-other",
        FALLBACK,
        root=str(tmp_path),
        rail_floors={"pl2": "invalid", "pl3": -1, "unknown": 20},
    )

    assert backend.supported is True
    assert backend._rail_floors == {}


def test_rail_floor_never_writes_above_live_ceiling(tmp_path):
    root = str(tmp_path)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl1_spl", 15, 5, 15)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl2_sppt", 10, 5, 10)
    _mk_attr(root, "lenovo-wmi-other-0", "ppt_pl3_fppt", 12, 5, 12)
    backend = FirmwareAttrBackend(
        "lenovo-wmi-other",
        FALLBACK,
        root=root,
        rail_floors={"pl2": 15, "pl3": 20},
    )

    backend.set_tdp(15, ac=True)

    rails = backend.observe().surfaces[backend.name]
    assert rails["pl2"].applied_w == 10
    assert rails["pl3"].applied_w == 12


def test_legion_go_2_profile_bumped_to_35(tmp_path):
    # Legion Go 2 (Z2 Extreme) sustains 35 W on battery (measured). Its profile drives
    # the range; the firmware read is irrelevant to the ceiling.
    dev = detect(product_name="83N0")
    assert (dev.tdp_max, dev.tdp_max_charger) == (30, 35)
