from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DeviceProfile:
    key: str                      # stable id, e.g. "rog_ally_x"
    display_name: str             # shown in DeviceHeader, e.g. "ROG Ally X"
    chip: str                     # e.g. "AMD Z1 Extreme"
    vendor: str                   # "amd" | "intel"
    tdp_min: int                  # watts
    tdp_default: int              # watts (sensible nominal)
    tdp_max: int                  # watts on battery
    tdp_max_charger: int          # watts when a compatible charger is connected (== tdp_max if none)
    # DMI product_name strings that identify this device (matched case-insensitively, substring)
    match_names: tuple = field(default_factory=tuple)
    is_generic: bool = False
    # When set, the UI shows the experimental marker for this recognised model.
    experimental: bool = False
    # Panel technology. "oled" hides the "OLED look" color preset (a real OLED has
    # nothing to emulate). A wrong guess only shows/hides a cosmetic button.
    panel: str = "lcd"
    # True on panels that support HDR output (gamescope can drive them in HDR). Gates
    # the HDR sub-tab; on a non-HDR panel the toggle would be a no-op, so it's hidden.
    hdr: bool = False
    # Optional per-model calibrated "OLED look" color state. None => the generic look
    # (display.oled_look.GENERIC_OLED_LOOK).
    oled_look: Optional[dict] = None
    # Curated quick-preset watts (quiet, balanced, turbo_battery, turbo_charger);
    # empty → fall back to (min, default, max, max_ac).
    tdp_presets: tuple = field(default_factory=tuple)
    # Ceiling unlocked when the user confirms the external cooler is attached (Win 5).
    cooler_max: Optional[int] = None


# Conservative, safe fallback when detection fails - visibly generic.
GENERIC = DeviceProfile(
    key="generic",
    display_name="Dispositivo genérico",
    chip="Desconocido",
    vendor="amd",
    tdp_min=4,
    tdp_default=10,
    # Ceiling for an unrecognised handheld on the ryzenadj path (no firmware bounds to
    # read). 30 W is the sustained max the modern AMD handheld category reaches with
    # active cooling; 15 W stranded capable devices far below their real limit. Devices
    # that go higher expose it via their firmware bounds once recognised.
    tdp_max=30,
    tdp_max_charger=30,
    match_names=(),
    is_generic=True,
)

# Ordered most-specific first (so "ROG Ally X" wins before "ROG Ally").
DEVICE_TABLE = (
    DeviceProfile("steam_deck_lcd", "Steam Deck", "AMD Van Gogh", "amd",
                  3, 12, 15, 15, match_names=("Jupiter",)),
    DeviceProfile("steam_deck_oled", "Steam Deck OLED", "AMD Sephiroth", "amd",
                  3, 12, 15, 15, match_names=("Galileo",), panel="oled", hdr=True),
    DeviceProfile("rog_xbox_ally_x", "ROG Xbox Ally X", "AMD Ryzen AI Z2 Extreme", "amd",
                  7, 17, 25, 35, match_names=("ROG Xbox Ally X",),
                  tdp_presets=(13, 17, 25, 30)),
    DeviceProfile("rog_xbox_ally", "ROG Xbox Ally", "AMD Ryzen Z2 A", "amd",
                  5, 13, 17, 20, match_names=("RC73YA",), experimental=True,
                  tdp_presets=(10, 15, 17, 20)),
    DeviceProfile("rog_ally_x", "ROG Ally X", "AMD Z1 Extreme", "amd",
                  7, 17, 25, 30, match_names=("ROG Ally X",),
                  tdp_presets=(13, 17, 25, 30)),
    DeviceProfile("rog_ally", "ROG Ally", "AMD Z1 Extreme", "amd",
                  7, 15, 25, 30, match_names=("ROG Ally RC71", "ROG Ally")),
    DeviceProfile("legion_go_2", "Legion Go 2", "AMD Ryzen AI Z2 Extreme", "amd",
                  5, 15, 30, 33, match_names=("83N0", "83N1", "Legion Go 2"),
                  panel="oled", hdr=True),
    # Legion Go S ships as both 8ARP1 (83L3) and 8APU1 (83N6), each with either a
    # Ryzen Z1 Extreme or a Z2 Go. The real chip is read live from /proc/cpuinfo;
    # this string is only a fallback when that read fails.
    DeviceProfile("legion_go_s", "Legion Go S", "AMD Ryzen Z1 Extreme / Z2 Go", "amd",
                  5, 15, 30, 33, match_names=("83L3", "83N6", "Legion Go S")),
    DeviceProfile("legion_go", "Legion Go", "AMD Z1 Extreme", "amd",
                  5, 15, 30, 30, match_names=("83E1", "Legion Go")),
    DeviceProfile("msi_claw_8_ai_plus", "MSI Claw 8 AI+", "Intel Core Ultra 7 258V", "intel",
                  8, 17, 30, 35, match_names=("Claw 8 AI+", "Claw 8")),
    # OneXPlayer OneXFly Apex (Strix Halo). The chip name is read live from
    # cpuinfo; this string is only a fallback.
    DeviceProfile("onexplayer_apex", "OneXPlayer OneXFly Apex",
                  "AMD Ryzen AI Max+ 395", "amd",
                  5, 20, 45, 54, match_names=("ONEXPLAYER APEX",), experimental=True),
    DeviceProfile("aokzoe_a1x", "AOKZOE A1X", "AMD Ryzen AI 9 HX 370", "amd",
                  4, 18, 30, 30, match_names=("AOKZOE A1X",), experimental=True,
                  tdp_presets=(12, 18, 30, 30)),
    DeviceProfile("gpd_win_mini_2025", "GPD Win Mini 2025",
                  "AMD Ryzen AI 9 HX 370", "amd",
                  5, 20, 35, 35, match_names=("G1617-02",), experimental=True,
                  tdp_presets=(12, 22, 32, 32)),
    DeviceProfile("msi_claw_a8", "MSI Claw A8", "AMD Ryzen Z2 Extreme", "amd",
                  6, 17, 35, 35, match_names=("Claw A8",), experimental=True,
                  tdp_presets=(10, 20, 33, 33)),
    DeviceProfile("onexplayer_f1pro", "OneXPlayer F1 Pro",
                  "AMD Ryzen AI 9 HX 370", "amd",
                  5, 18, 30, 30, match_names=("ONEXPLAYER F1Pro",), experimental=True,
                  tdp_presets=(12, 18, 30, 30)),
    DeviceProfile("gpd_win5", "GPD Win 5", "AMD Ryzen AI Max 385", "amd",
                  5, 25, 55, 55, match_names=("G1618-05",), experimental=True,
                  tdp_presets=(15, 30, 50, 50), cooler_max=75),
    DeviceProfile("gpd_win_max_2", "GPD Win Max 2", "AMD Ryzen 7 8840U", "amd",
                  5, 20, 35, 35, match_names=("G1619-05",), experimental=True,
                  tdp_presets=(12, 22, 32, 32)),
)
