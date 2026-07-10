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
    "Claw 8 AI+ A2VM": "msi_claw_8_ai_plus",
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


def test_known_devices_are_not_experimental():
    for product in ("Galileo", "ROG Ally X RC72LA_RC72LA", "83N0", "Claw 8 AI+ A2VM"):
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


def test_ally_x_has_charger_boost():
    prof = detect(product_name="ROG Ally X RC72LA_RC72LA")
    assert prof.tdp_max == 25
    assert prof.tdp_max_charger == 30
    assert prof.tdp_max_charger > prof.tdp_max


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
