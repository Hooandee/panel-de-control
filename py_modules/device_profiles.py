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
    # Optional per-model calibrated "OLED look" color state. None => the generic look
    # (display.oled_look.GENERIC_OLED_LOOK).
    oled_look: Optional[dict] = None


# Conservative, safe fallback when detection fails - visibly generic.
GENERIC = DeviceProfile(
    key="generic",
    display_name="Dispositivo genérico",
    chip="Desconocido",
    vendor="amd",
    tdp_min=4,
    tdp_default=10,
    tdp_max=15,
    tdp_max_charger=15,
    match_names=(),
    is_generic=True,
)

# Ordered most-specific first (so "ROG Ally X" wins before "ROG Ally").
DEVICE_TABLE = (
    DeviceProfile("steam_deck_lcd", "Steam Deck", "AMD Van Gogh", "amd",
                  3, 12, 15, 15, match_names=("Jupiter",)),
    DeviceProfile("steam_deck_oled", "Steam Deck OLED", "AMD Sephiroth", "amd",
                  3, 12, 15, 15, match_names=("Galileo",), panel="oled"),
    DeviceProfile("rog_xbox_ally_x", "ROG Xbox Ally X", "AMD Ryzen AI Z2 Extreme", "amd",
                  7, 17, 25, 30, match_names=("ROG Xbox Ally X",)),
    DeviceProfile("rog_ally_x", "ROG Ally X", "AMD Z1 Extreme", "amd",
                  7, 17, 25, 30, match_names=("ROG Ally X",)),
    DeviceProfile("rog_ally", "ROG Ally", "AMD Z1 Extreme", "amd",
                  7, 15, 25, 30, match_names=("ROG Ally RC71", "ROG Ally")),
    DeviceProfile("legion_go_2", "Legion Go 2", "AMD Ryzen AI Z2 Extreme", "amd",
                  5, 15, 30, 33, match_names=("83N0", "Legion Go 2"), panel="oled"),
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
)
