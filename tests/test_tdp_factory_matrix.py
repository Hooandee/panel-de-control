import os

from device_profiles import DEVICE_TABLE, GENERIC
from tdp.factory import select_backend


def _profile(key):
    return next(profile for profile in DEVICE_TABLE if profile.key == key)


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _mk_legacy_asus(root):
    base = os.path.join(root, "sys/devices/platform/asus-nb-wmi")
    for leaf, value in (
        ("ppt_pl1_spl", 15),
        ("ppt_pl2_sppt", 20),
        ("ppt_fppt", 25),
    ):
        _write(os.path.join(base, leaf), value)


def _mk_firmware(root, provider):
    base = os.path.join(root, "sys/class/firmware-attributes", provider, "attributes")
    for attr, maximum in (
        ("ppt_pl1_spl", 35),
        ("ppt_pl2_sppt", 45),
        ("ppt_pl3_fppt", 55),
    ):
        path = os.path.join(base, attr)
        _write(os.path.join(path, "current_value"), 15)
        _write(os.path.join(path, "min_value"), 5)
        _write(os.path.join(path, "max_value"), maximum)


def _mk_dptc(root):
    _mk_firmware(root, "amd-dptc")
    base = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    _write(os.path.join(base, "name"), "amd-dptc")
    _write(os.path.join(base, "profile"), "balanced")
    _write(
        os.path.join(base, "choices"),
        "low-power balanced performance custom",
    )


def _mk_board(root, board_name):
    _write(os.path.join(root, "sys/class/dmi/id/board_name"), board_name)


def _no_ryzenadj():
    return None


def test_rog_ally_selects_standalone_legacy_backend(tmp_path):
    root = str(tmp_path)
    _mk_legacy_asus(root)

    backend = select_backend(
        _profile("rog_ally"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="anatase",
    )

    assert backend.name == "asus-nb-wmi"
    assert [item["candidate"] for item in backend.probe_trace] == [
        "asus",
        "asus_nb_wmi",
    ]


def test_rog_with_armoury_and_legacy_keeps_coordinated_backend(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "asus-armoury")
    _mk_legacy_asus(root)

    backend = select_backend(
        _profile("rog_ally"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="anatase",
    )

    assert backend.name == "firmware-attr:asus-armoury"
    assert [item["candidate"] for item in backend.probe_trace] == ["asus"]


def test_known_rog_does_not_probe_dptc_or_other_vendor_firmware(tmp_path):
    root = str(tmp_path)
    _mk_dptc(root)
    _mk_firmware(root, "lenovo-wmi-other")
    _mk_firmware(root, "msi-wmi-platform")

    backend = select_backend(
        _profile("rog_ally"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="anatase",
    )

    assert backend.supported is False
    assert [item["candidate"] for item in backend.probe_trace] == [
        "asus",
        "asus_nb_wmi",
        "ryzenadj",
        "alib",
    ]


def test_amd_dptc_is_first_for_supported_non_vendor_specific_families(tmp_path):
    keys = (
        "onexplayer_apex",
        "aokzoe_a1x",
        "gpd_win_mini_2025",
        "onexplayer_f1pro",
        "gpd_win5",
        "gpd_win_max_2",
    )
    for key in keys:
        root = str(tmp_path / key)
        _mk_dptc(root)

        backend = select_backend(
            _profile(key),
            root=root,
            ryzenadj_resolve=_no_ryzenadj,
            os_id="anatase",
        )

        assert backend.name == "amd-dptc"
        assert [item["candidate"] for item in backend.probe_trace] == ["dptc"]


def test_dptc_does_not_change_steam_deck_legion_msi_or_rog(tmp_path):
    keys = (
        "steam_deck_lcd",
        "steam_deck_oled",
        "rog_ally",
        "legion_go",
        "legion_go_2",
        "msi_claw_8_ai_plus",
        "msi_claw_a8",
    )
    for key in keys:
        root = str(tmp_path / key)
        _mk_dptc(root)

        backend = select_backend(
            _profile(key),
            root=root,
            ryzenadj_resolve=_no_ryzenadj,
            os_id="anatase",
        )

        assert backend.name != "amd-dptc"


def test_msi_a8_exact_board_prefers_its_native_backend(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "msi-wmi-platform")
    _mk_board(root, "MS-1T8K")

    backend = select_backend(
        _profile("msi_claw_a8"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="anatase",
    )

    assert backend.name == "msi-claw-a8-firmware"
    assert [item["candidate"] for item in backend.probe_trace] == ["msi_a8"]


def test_msi_a8_nearby_board_falls_back_without_touching_intel_chain(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "msi-wmi-platform")
    _mk_board(root, "MS-1T42")

    amd_backend = select_backend(
        _profile("msi_claw_a8"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
        os_id="anatase",
    )
    intel_backend = select_backend(
        _profile("msi_claw_8_ai_plus"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
        os_id="anatase",
    )

    assert amd_backend.name == "ryzenadj"
    assert [item["candidate"] for item in amd_backend.probe_trace] == [
        "msi_a8",
        "ryzenadj",
    ]
    assert intel_backend.name == "firmware-attr:msi-wmi-platform"
    assert [item["candidate"] for item in intel_backend.probe_trace] == ["msi"]


def test_generic_amd_prefers_complete_dptc_with_conservative_profile(tmp_path):
    root = str(tmp_path)
    _mk_dptc(root)

    backend = select_backend(
        GENERIC,
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
        os_id="anatase",
    )

    assert backend.name == "amd-dptc"
    assert backend.get_limits().max_ac_w == GENERIC.tdp_max_charger


def test_non_anatase_keeps_historical_rog_fallback_chain(tmp_path):
    root = str(tmp_path)
    _mk_legacy_asus(root)
    _mk_dptc(root)

    backend = select_backend(
        _profile("rog_ally"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="bazzite",
    )

    assert backend.supported is False
    assert [item["candidate"] for item in backend.probe_trace] == [
        "asus",
        "lenovo",
        "msi",
        "ryzenadj",
        "alib",
    ]


def test_bazzite_legion_go_2_prefers_lenovo_firmware(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "lenovo-wmi-other-0")

    backend = select_backend(
        _profile("legion_go_2"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
        os_id="bazzite",
    )

    assert backend.name == "firmware-attr:lenovo-wmi-other"
    assert [item["candidate"] for item in backend.probe_trace] == ["lenovo"]


def test_bazzite_legion_go_2_keeps_ryzenadj_fallback(tmp_path):
    backend = select_backend(
        _profile("legion_go_2"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
        os_id="bazzite",
    )

    assert backend.name == "ryzenadj"
    assert [item["candidate"] for item in backend.probe_trace] == [
        "lenovo",
        "asus",
        "msi",
        "ryzenadj",
    ]


def test_gpd_win5_dptc_keeps_safe_ceiling_and_exposes_cooler_headroom(tmp_path):
    root = str(tmp_path)
    _mk_dptc(root)
    base = os.path.join(
        root,
        "sys/class/firmware-attributes/amd-dptc/attributes",
    )
    _write(os.path.join(base, "ppt_pl1_spl/max_value"), 80)
    _write(os.path.join(base, "ppt_pl2_sppt/max_value"), 90)
    _write(os.path.join(base, "ppt_pl3_fppt/max_value"), 100)

    backend = select_backend(
        _profile("gpd_win5"),
        root=root,
        ryzenadj_resolve=_no_ryzenadj,
        os_id="anatase",
    )

    assert backend.get_limits().max_w == 55
    assert backend.get_limits().max_ac_w == 55
    assert backend.level_limits() == {
        "pl1": {"min": 5, "max": 75},
        "pl2": {"min": 5, "max": 90},
        "pl3": {"min": 5, "max": 100},
    }
    assert backend.cap_boost_to_active is True
