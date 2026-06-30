from tdp.types import TdpLimits

_L = TdpLimits(min_w=7, default_w=17, max_w=25, max_ac_w=35)


def test_unlock_off_is_noop():
    assert _L.unlocked(False) is _L


def test_unlock_raises_battery_max_to_charger_max():
    u = _L.unlocked(True)
    assert u.max_w == 35
    assert u.max_ac_w == 35
    assert u.min_w == 7 and u.default_w == 17


def test_unlock_clamp_on_battery_allows_full_max():
    u = _L.unlocked(True)
    assert u.clamp(35, on_ac=False) == 35   # battery now allows the firmware max
    assert _L.clamp(35, on_ac=False) == 25  # locked: still capped at battery policy


def test_unlock_noop_when_battery_already_equals_charger():
    flat = TdpLimits(3, 12, 15, 15)
    assert flat.unlocked(True) is flat
