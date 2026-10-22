import pytest

from device_profiles import DESKTOP_PC, DEVICE_TABLE, GENERIC, GENERIC_ARM

_PROFILES = {profile.key: profile for profile in (*DEVICE_TABLE, GENERIC, DESKTOP_PC, GENERIC_ARM)}

# machine, ladder elsewhere, ladder on Anatase, ryzenadj readback policy
_LADDERS = (
    ("steam_machine", ('asus', 'lenovo', 'msi'), ('asus', 'lenovo', 'msi'), None),
    ("steam_deck_lcd", ('deck',), ('deck',), None),
    ("steam_deck_oled", ('deck',), ('deck',), None),
    ("rog_xbox_ally_x", ('asus', 'asus_nb_wmi', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('asus', 'asus_nb_wmi', 'ryzenadj', 'alib'), 'normal'),
    ("rog_xbox_ally", ('asus', 'asus_nb_wmi', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('asus', 'asus_nb_wmi', 'ryzenadj', 'alib'), 'normal'),
    ("rog_ally_x", ('asus', 'asus_nb_wmi', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('asus', 'asus_nb_wmi', 'ryzenadj', 'alib'), 'normal'),
    ("rog_ally", ('asus', 'asus_nb_wmi', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('asus', 'asus_nb_wmi', 'ryzenadj', 'alib'), 'normal'),
    ("legion_go_2", ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("legion_go_s", ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("legion_go", ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), ('lenovo', 'asus', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("msi_claw_8_ai_plus", ('msi', 'intel'), ('msi', 'intel'), 'normal'),
    ("onexplayer_apex", ('ryzenadj', 'ryzenadj_unverified', 'alib'), ('dptc', 'ryzenadj', 'ryzenadj_unverified', 'alib'), 'normal'),
    ("onexplayer_superx", ('asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), 'strict'),
    ("onexplayer_x2_mini_pro", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("onexplayer_3", ('msi', 'intel'), ('msi', 'intel'), 'normal'),
    ("zotac_gaming_zone", ('asus', 'lenovo', 'msi', 'ryzenadj'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj'), 'strict'),
    ("rog_flow_z13", ('asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), 'strict'),
    ("onexplayer_f1", ('asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), 'strict'),
    ("ayaneo_3", ('asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'ryzenadj_unverified', 'alib'), 'strict'),
    ("aokzoe_a1x", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("gpd_win_mini_2025", ('asus', 'lenovo', 'msi', 'ryzenadj'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj'), 'strict'),
    ("msi_claw_a8", ('ryzenadj',), ('msi_a8', 'ryzenadj'), 'normal'),
    ("onexplayer_f1pro", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("gpd_win5", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("gpd_win_max_2", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("generic", ('asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), ('dptc', 'asus', 'lenovo', 'msi', 'ryzenadj', 'alib'), 'normal'),
    ("desktop_pc", (), (), None),
    ("generic_arm", ('arm_levels',), ('arm_levels',), 'normal'),
)


def test_every_profile_has_a_pinned_ladder():
    assert {row[0] for row in _LADDERS} == set(_PROFILES)


@pytest.mark.parametrize(("key", "elsewhere", "anatase", "ryzenadj"), _LADDERS)
def test_machine_route_ladder(key, elsewhere, anatase, ryzenadj):
    profile = _PROFILES[key]
    routes = profile.tdp_routes

    assert routes.chain(arch=profile.arch, vendor=profile.vendor, os_id=None) == elsewhere
    assert routes.chain(arch=profile.arch, vendor=profile.vendor, os_id="anatase") == anatase
    assert routes.ryzenadj == ryzenadj


def test_only_zotac_writes_ryzenadj_without_its_first_readback():
    assert {key for key, profile in _PROFILES.items()
            if profile.tdp_routes.ryzenadj_readback_fallback} == {"zotac_gaming_zone"}


def test_unreadable_ryzenadj_yields_on_the_measured_ladders():
    assert {key for key, profile in _PROFILES.items()
            if profile.tdp_routes.ryzenadj_yields_when_unreadable} == {
        "onexplayer_apex", "onexplayer_superx", "rog_flow_z13", "onexplayer_f1", "ayaneo_3",
    }
