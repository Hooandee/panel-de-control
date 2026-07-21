import os

from device_registry import detect


# (product_name as it appears in /sys/class/dmi/id/product_name) -> expected key
KNOWN = {
    "Jupiter": "steam_deck_lcd",
    "Galileo": "steam_deck_oled",
    "ROG Ally RC71L_RC71L": "rog_ally",
    "ROG Ally X RC72LA_RC72LA": "rog_ally_x",
    "ROG Xbox Ally X RC73XA": "rog_xbox_ally_x",
    "83E1": "legion_go",
    "83L3": "legion_go_s",           # Legion Go S 8ARP1 (Z1 Extreme / Z2 Go)
    "83L30030US": "legion_go_s",     # 8ARP1 SteamOS SKU
    "83N6": "legion_go_s",           # Legion Go S 8APU1 (Ryzen Z2 Go, 2025)
    "83N6000MSB": "legion_go_s",     # 8APU1 full SKU
    "83N0": "legion_go_2",           # Legion Go 2 — must NOT collide with 83N6
    "83N1": "legion_go_2",           # Legion Go 2 with the Ryzen Z2 (non-Extreme)
    "Claw 8 AI+ A2VM": "msi_claw_8_ai_plus",
    "ROG Xbox Ally RC73YA_RC73YA": "rog_xbox_ally",
}


def test_detects_each_known_device():
    for product, key in KNOWN.items():
        prof = detect(product_name=product)
        assert prof.key == key, f"{product!r} -> {prof.key} (expected {key})"


def test_intel_vs_amd_vendor():
    assert detect(product_name="Galileo").vendor == "amd"
    assert detect(product_name="Claw 8 AI+ A2VM").vendor == "intel"


def test_unknown_falls_back_to_generic_visibly():
    prof = detect(product_name="Some Random Laptop 9000")
    assert prof.key == "generic"
    assert prof.is_generic is True


def test_onexplayer_apex_is_recognised_experimental():
    prof = detect(product_name="ONEXPLAYER APEX")
    assert prof.key == "onexplayer_apex"
    assert prof.is_generic is False
    assert prof.experimental is True
    assert prof.vendor == "amd"


def test_onexplayer_apex_matches_case_insensitively():
    prof = detect(product_name="OneXPlayer Apex 2025")
    assert prof.key == "onexplayer_apex"


def test_aokzoe_a1x_is_recognised_experimental():
    prof = detect(product_name="AOKZOE A1X")
    assert prof.key == "aokzoe_a1x"
    assert prof.is_generic is False
    assert prof.experimental is True
    assert prof.vendor == "amd"
    assert prof.tdp_max == 30
    assert prof.tdp_presets == (12, 18, 30, 30)


def test_aokzoe_a1x_matches_case_insensitively():
    prof = detect(product_name="AOKZOE A1X Handheld")
    assert prof.key == "aokzoe_a1x"


def test_gpd_win_mini_2025_is_recognised_experimental():
    prof = detect(product_name="G1617-02")
    assert prof.key == "gpd_win_mini_2025"
    assert prof.is_generic is False
    assert prof.experimental is True
    assert prof.vendor == "amd"
    assert prof.tdp_max == 35
    assert prof.tdp_presets == (12, 22, 32, 32)


def test_msi_claw_a8_is_recognised_experimental():
    prof = detect(product_name="Claw A8 BZ2EM")
    assert prof.key == "msi_claw_a8"
    assert prof.is_generic is False
    assert prof.experimental is True
    assert prof.vendor == "amd"
    assert prof.tdp_max == 35
    assert prof.tdp_presets == (10, 20, 33, 33)


def test_msi_claw_a8_is_not_the_intel_claw():
    assert detect(product_name="Claw A8 BZ2EM").key == "msi_claw_a8"
    assert detect(product_name="Claw 8 AI+ A2VM").key == "msi_claw_8_ai_plus"


def test_rog_xbox_ally_z2a_is_recognised_and_capped():
    prof = detect(product_name="ROG Xbox Ally RC73YA_RC73YA")
    assert prof.key == "rog_xbox_ally"
    assert prof.experimental is True
    assert prof.vendor == "amd"
    assert prof.tdp_max == 17
    assert prof.tdp_max_charger == 20
    assert prof.tdp_presets == (10, 15, 17, 20)


def test_rog_xbox_ally_z2a_is_not_the_x():
    assert detect(product_name="ROG Xbox Ally RC73YA_RC73YA").key == "rog_xbox_ally"
    assert detect(product_name="ROG Xbox Ally X RC73XA").key == "rog_xbox_ally_x"


def test_onexplayer_f1pro_is_recognised_experimental():
    prof = detect(product_name="ONEXPLAYER F1Pro")
    assert prof.key == "onexplayer_f1pro"
    assert prof.experimental is True
    assert prof.tdp_max == 30
    assert prof.tdp_presets == (12, 18, 30, 30)


def test_gpd_win5_is_recognised_experimental():
    prof = detect(product_name="G1618-05")
    assert prof.key == "gpd_win5"
    assert prof.experimental is True
    assert prof.tdp_max == 55
    assert prof.tdp_presets == (15, 30, 50, 50)
    assert prof.cooler_max == 75  # cooler-attached ceiling (opt-in)


def test_only_win5_has_cooler_max():
    assert detect(product_name="G1619-05").cooler_max is None  # GPD Win Max 2
    assert detect(product_name="ONEXPLAYER F1Pro").cooler_max is None
    assert detect(product_name="Some Random Laptop").cooler_max is None


def test_gpd_win_max_2_is_recognised_experimental():
    prof = detect(product_name="G1619-05")
    assert prof.key == "gpd_win_max_2"
    assert prof.experimental is True
    assert prof.tdp_max == 35


def test_known_devices_are_not_experimental():
    for product in ("Galileo", "ROG Ally X RC72LA_RC72LA", "83N0", "83N1", "Claw 8 AI+ A2VM"):
        assert detect(product_name=product).experimental is False


def test_generic_fallback_is_not_experimental():
    assert detect(product_name="Some Random Laptop 9000").experimental is False


def _mk_cpuinfo(root, vendor_id, model_name):
    os.makedirs(os.path.join(root, "proc"), exist_ok=True)
    with open(os.path.join(root, "proc", "cpuinfo"), "w") as f:
        f.write(f"vendor_id\t: {vendor_id}\nmodel name\t: {model_name}\n")


def test_generic_reads_real_vendor_and_chip_amd(tmp_path):
    root = str(tmp_path)
    _mk_cpuinfo(root, "AuthenticAMD", "AMD Ryzen Z2 Extreme w/ Radeon 890M")
    prof = detect(product_name="Unknown Handheld", root=root)
    assert prof.is_generic is True
    assert prof.vendor == "amd"
    assert "Ryzen Z2 Extreme" in prof.chip


def test_generic_reads_real_vendor_intel(tmp_path):
    root = str(tmp_path)
    _mk_cpuinfo(root, "GenuineIntel", "Intel Core Ultra 7 258V")
    prof = detect(product_name="Unknown Handheld", root=root)
    assert prof.is_generic is True
    assert prof.vendor == "intel"
    assert "Core Ultra" in prof.chip


def test_generic_defaults_to_amd_when_cpuinfo_absent(tmp_path):
    prof = detect(product_name="Unknown Handheld", root=str(tmp_path))
    assert prof.is_generic is True
    assert prof.vendor == "amd"


def test_generic_profile_ceiling_allows_modern_amd_range():
    # An unrecognised AMD handheld on the ryzenadj path has no firmware bounds to read,
    # so the generic profile ceiling IS the slider max. It must not strand a capable
    # handheld at 15 W — the category sustains ~30 W with active cooling.
    from device_profiles import GENERIC
    assert GENERIC.tdp_max >= 30
    assert GENERIC.tdp_max_charger >= 30


def test_ally_x_has_charger_boost():
    prof = detect(product_name="ROG Ally X RC72LA_RC72LA")
    assert prof.tdp_max == 25
    assert prof.tdp_max_charger == 30
    assert prof.tdp_max_charger > prof.tdp_max


def test_legion_go_s_reaches_firmware_ceilings():
    for name in ("83L3", "83N6"):
        prof = detect(product_name=name)
        assert prof.key == "legion_go_s"
        assert prof.tdp_max == 33          # sustained ceiling on battery
        assert prof.tdp_max_charger == 40  # extra reachable only on charger
        assert prof.charger_only_extra is True


def test_deck_has_no_charger_boost():
    prof = detect(product_name="Galileo")
    assert prof.tdp_max == 15
    assert prof.tdp_max_charger == prof.tdp_max  # no boost


def test_ally_family_curated_presets():
    for name in ("ROG Ally X RC72LA_RC72LA", "ROG Xbox Ally X RC73XA"):
        prof = detect(product_name=name)
        assert prof.tdp_presets == (13, 17, 25, 30)


def test_other_devices_have_no_curated_presets():
    assert detect(product_name="Galileo").tdp_presets == ()  # falls back to rail limits


def test_gpu_generation():
    from device_registry import gpu_generation
    assert gpu_generation("intel", "Intel Core Ultra 7 258V") == "intel"
    assert gpu_generation("amd", "AMD Sephiroth") == "rdna2"
    assert gpu_generation("amd", "AMD Van Gogh") == "rdna2"
    assert gpu_generation("amd", "AMD Z1 Extreme") == "rdna3"
    assert gpu_generation("amd", "AMD Ryzen Z2 Go") == "rdna2"
    assert gpu_generation("amd", "AMD Ryzen AI Z2 Extreme") == "rdna35"
    assert gpu_generation("amd", "AMD Ryzen AI 9 HX 370") == "rdna35"
    assert gpu_generation("amd", "AMD Ryzen AI Max+ 395") == "rdna35"
    assert gpu_generation("amd", "AMD Ryzen Z2 A") == "rdna2"
    assert gpu_generation("amd", "Desconocido") == "unknown"
