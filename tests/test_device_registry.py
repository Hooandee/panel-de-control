from device_registry import detect
from device_profiles import GENERIC


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
    assert prof is GENERIC
    assert prof.key == "generic"
    assert prof.is_generic is True


def test_ally_x_has_charger_boost():
    prof = detect(product_name="ROG Ally X RC72LA_RC72LA")
    assert prof.tdp_max == 25
    assert prof.tdp_max_charger == 30
    assert prof.tdp_max_charger > prof.tdp_max


def test_deck_has_no_charger_boost():
    prof = detect(product_name="Galileo")
    assert prof.tdp_max == 15
    assert prof.tdp_max_charger == prof.tdp_max  # no boost
