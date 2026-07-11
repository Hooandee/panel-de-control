from device_profiles import DEVICE_TABLE
from tdp.types import TdpLimits, TdpResult


def _profile(key):
    return next(p for p in DEVICE_TABLE if p.key == key)


def test_limits_clamp():
    lim = TdpLimits(min_w=5, default_w=15, max_w=25, max_ac_w=30)
    assert lim.clamp(2) == 5
    assert lim.clamp(99) == 30
    assert lim.clamp(20) == 20
    assert lim.clamp(99, on_ac=False) == 25  # battery ceiling
    assert lim.clamp(99, on_ac=True) == 30   # charger ceiling


def test_limits_from_profile_maps_fields():
    lim = TdpLimits.from_profile(_profile("rog_ally_x"))
    assert lim.min_w == _profile("rog_ally_x").tdp_min
    assert lim.default_w == _profile("rog_ally_x").tdp_default
    assert lim.max_w == _profile("rog_ally_x").tdp_max
    assert lim.max_ac_w == _profile("rog_ally_x").tdp_max_charger


def test_result_fields():
    r = TdpResult(requested_w=15, applied_w=15, ok=True, detail="")
    assert r.ok and r.applied_w == 15 and r.requested_w == 15


def test_with_cooler_raises_ceiling():
    lim = TdpLimits(min_w=5, default_w=25, max_w=55, max_ac_w=55)
    boosted = lim.with_cooler(75)
    assert boosted.max_w == 75
    assert boosted.max_ac_w == 75
    assert boosted.min_w == 5 and boosted.default_w == 25


def test_with_cooler_noop_when_not_higher():
    lim = TdpLimits(min_w=5, default_w=25, max_w=55, max_ac_w=55)
    assert lim.with_cooler(50) is lim
    assert lim.with_cooler(55) is lim
