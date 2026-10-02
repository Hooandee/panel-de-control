from device_profiles import DESKTOP_PC, DEVICE_TABLE, GENERIC
from tdp.extra_range import extra_tdp_max_ac, is_strix_halo


def _profile(key):
    return next(profile for profile in DEVICE_TABLE if profile.key == key)


def test_amd_handhelds_reach_forty_watts_on_the_charger():
    assert extra_tdp_max_ac(_profile("rog_ally_x")) == 40
    assert extra_tdp_max_ac(_profile("zotac_gaming_zone")) == 40
    assert extra_tdp_max_ac(GENERIC) == 40


def test_no_extra_when_the_safe_ceiling_already_reaches_it():
    assert extra_tdp_max_ac(_profile("legion_go_s")) is None


def test_strix_halo_reaches_one_hundred_twenty():
    for key in ("onexplayer_apex", "onexplayer_superx", "onexplayer_x2_mini_pro",
                "rog_flow_z13", "gpd_win5"):
        assert is_strix_halo(_profile(key))
        assert extra_tdp_max_ac(_profile(key)) == 120


def test_no_extra_on_intel_steam_hardware_or_desktops():
    for key in ("msi_claw_8_ai_plus", "onexplayer_3", "steam_deck_lcd",
                "steam_deck_oled", "steam_machine"):
        assert extra_tdp_max_ac(_profile(key)) is None
    assert extra_tdp_max_ac(DESKTOP_PC) is None
