from device_profiles import DEVICE_TABLE
from tdp.write_ceilings import charger_write_max, cooler_write_max


def _profile(key):
    return next(profile for profile in DEVICE_TABLE if profile.key == key)


def test_charger_only_cooler_raises_only_the_charger_ceiling():
    apex = _profile("onexplayer_apex")
    assert cooler_write_max(apex) is None
    assert charger_write_max(apex) == 120


def test_cooler_without_charger_restriction_raises_both_ceilings():
    assert cooler_write_max(_profile("gpd_win5")) == 75


def test_warned_unlock_is_a_charger_ceiling():
    assert charger_write_max(_profile("onexplayer_3")) == 45


def test_profiles_without_opt_ins_have_no_extra_ceiling():
    deck = _profile("steam_deck_oled")
    assert cooler_write_max(deck) is None
    assert charger_write_max(deck) is None


def test_charger_ceiling_includes_the_manual_extra_range():
    assert charger_write_max(_profile("rog_ally_x")) == 40
    assert charger_write_max(_profile("gpd_win5")) == 120


def test_charger_only_cooler_and_extra_take_the_higher():
    assert charger_write_max(_profile("onexplayer_apex")) == 120
