"""Cooperative InputPlumber remap: which physical buttons a device exposes (by
their silkscreen name), and how to apply an override without clobbering the
device's default mappings.

Design (validated ON-DEVICE, 2026-07-04):
- The remappable buttons come from a PER-DEVICE table (DEVICE_BUTTONS), NOT from the
  daemon's live Capabilities. Capabilities is a superset with phantoms (the Go 2
  advertises paddle caps no physical button emits) and it can't tell you the
  silkscreen name (M1 is reported as `RightStickTouch`); the SAME capability is a
  different physical button per device (LeftPaddle1 = Go2 "Y1" but Claw "M2"). So
  each entry maps a source capability to the literal silkscreen label, validated by
  pressing every button on real hardware. The table is intersected with the live
  capability set (defensive — never surface a button the daemon doesn't report).
- Applying an override PRESERVES the device's default profile: we read the current
  profile, replace only the edited button's target, and load it back. The YAML
  round-trip runs in the SYSTEM python (which has PyYAML) via subprocess — Decky's
  frozen backend may not bundle PyYAML. The MERGE itself is a pure function here so
  it's unit-tested; only load()/dump() live in the system-python helper.
"""

# The remappable PHYSICAL buttons per device, validated ON-DEVICE (2026-07-04) by
# pressing each one and reading the source capability it emits. This is a
# per-device table, NOT derived from the daemon's Capabilities property, because:
#   - Capabilities is a SUPERSET with phantoms (the Go 2 lists LeftPaddle3/
#     RightPaddle3 that no physical button emits) — deriving from it showed ghosts;
#   - the SAME capability is a DIFFERENT physical button per device (LeftPaddle1 is
#     the Go 2's "Y1" but the Claw's "M2") — labels must be per-device;
#   - a capability's normalized name (RightStickTouch) rarely matches the silkscreen
#     label the user reads (M1) — the user wants the silkscreen name.
# ONLY the grip/paddle buttons are listed: system buttons (Guide/QuickAccess/
# QuickAccess2/Keyboard) are deliberately omitted — remapping them breaks Steam/QAM
# navigation. Each entry is (source_capability, silkscreen_label). Labels are the
# literal names printed on the device and are NOT translated. An unlisted device
# degrades to an empty (honest) button list — never invents a mapping.
DEVICE_BUTTONS = {
    "legion_go_2": [
        ("LeftPaddle1", "Y1"), ("LeftPaddle2", "Y2"), ("RightPaddle1", "Y3"),
        ("RightStickTouch", "M1"), ("LeftStickTouch", "M2"), ("RightPaddle2", "M3"),
    ],
    "legion_go": [
        # Go 1: M1 emits a mouse/keyboard event (not a gamepad cap) → not remappable.
        ("LeftPaddle1", "Y1"), ("LeftPaddle2", "Y2"), ("RightPaddle1", "Y3"),
        ("LeftStickTouch", "M2"), ("RightPaddle2", "M3"),
    ],
    "msi_claw_8_ai_plus": [
        ("RightPaddle1", "M1"), ("LeftPaddle1", "M2"),
    ],
}

# Gamepad buttons offered as remap targets (what an extra button can become).
GAMEPAD_TARGETS = (
    "South", "North", "East", "West",
    "LeftBumper", "RightBumper", "LeftTrigger", "RightTrigger",
    "LeftStick", "RightStick",
    "DPadUp", "DPadDown", "DPadLeft", "DPadRight",
    "Start", "Select", "Guide",
    "LeftPaddle1", "RightPaddle1", "LeftPaddle2", "RightPaddle2",
    "Screenshot",
)

# Keyboard keys offered as remap targets (common shortcuts).
KEY_TARGETS = (
    "KeyEsc", "KeyEnter", "KeySpace", "KeyTab",
    "KeyVolumeUp", "KeyVolumeDown", "KeyMute",
    "KeyBrightnessUp", "KeyBrightnessDown",
    "KeyLeftCtrl", "KeyLeftShift", "KeyLeftAlt",
)


def _capability_names(capabilities) -> set:
    """Short names ('RightPaddle1') of the live capability strings
    ('Gamepad:Button:RightPaddle1')."""
    return {
        cap.rsplit(":", 1)[-1]
        for cap in (capabilities or [])
        if isinstance(cap, str)
    }


def buttons_for(device_key, capabilities) -> list:
    """The remappable physical buttons for this device as [(capability, silkscreen)],
    in display order. The per-device table is the source of truth for which buttons
    and what to call them; it's intersected with the LIVE capability set so we only
    surface a button the daemon actually reports (defensive — never invent one). An
    unknown device (not in the validated table) yields an empty list."""
    have = _capability_names(capabilities)
    return [
        (cap, label)
        for (cap, label) in DEVICE_BUTTONS.get(device_key or "", [])
        if cap in have
    ]


def is_known_device(device_key) -> bool:
    """Whether we have an on-device-validated button map for this device."""
    return device_key in DEVICE_BUTTONS


def sanitize_target(target: dict):
    """Coerce one target to {"gamepad"|"key": name}, or None if invalid (never-fake)."""
    if not isinstance(target, dict):
        return None
    if target.get("gamepad") in GAMEPAD_TARGETS:
        return {"gamepad": target["gamepad"]}
    if target.get("key") in KEY_TARGETS:
        return {"key": target["key"]}
    return None


def sanitize_targets(targets) -> list:
    if not isinstance(targets, (list, tuple)):
        return []
    return [s for t in targets if (s := sanitize_target(t)) is not None]


def _target_event(target: dict) -> dict:
    """Our internal target → an InputPlumber target_event dict."""
    if "gamepad" in target:
        return {"gamepad": {"button": target["gamepad"]}}
    return {"keyboard": target["key"]}


def _mapping_entry(button: str, targets: list) -> dict:
    return {
        "name": button,
        "source_event": {"gamepad": {"button": button}},
        "target_events": [_target_event(t) for t in targets],
    }


def apply_overrides_to_profile(profile: dict, overrides: dict) -> dict:
    """Return a copy of `profile` with each override applied to its button's entry.

    Pure: preserves every existing mapping (dials, untouched buttons) and only
    replaces the target of an overridden button (adding an entry if absent). An
    empty/absent override list removes our entry so the button reverts to default.
    """
    prof = dict(profile or {})
    mapping = list(prof.get("mapping") or [])

    def source_button(entry):
        se = entry.get("source_event", {}) if isinstance(entry, dict) else {}
        return se.get("gamepad", {}).get("button")

    for button, targets in overrides.items():
        clean = sanitize_targets(targets)
        mapping = [e for e in mapping if source_button(e) != button]  # drop old
        if clean:
            mapping.append(_mapping_entry(button, clean))
    prof["mapping"] = mapping
    return prof
