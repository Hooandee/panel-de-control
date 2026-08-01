"""Cooperative InputPlumber remap: which physical buttons a device exposes (by
their silkscreen name), and how to apply an override without clobbering the
device's default mappings.

Design:
- The remappable buttons come from a PER-DEVICE table (DEVICE_BUTTONS), NOT from the
  daemon's live Capabilities. Capabilities is a superset with phantoms (the Go 2
  advertises paddle caps no physical button emits) and it can't tell you the
  silkscreen name (M1 is reported as `RightStickTouch`); the SAME capability is a
  different physical button per device (LeftPaddle1 = Go2 "Y1" but Claw "M2"). So
  each entry maps a source capability to the literal silkscreen label. The table is
  intersected with the live capability set (defensive — never surface a button the
  daemon doesn't report).
- Applying an override PRESERVES the device's default profile: we read the current
  profile, replace only the edited button's target, and load it back. The YAML
  round-trip runs in the SYSTEM python (which has PyYAML) via subprocess — Decky's
  frozen backend may not bundle PyYAML. The MERGE itself is a pure function here so
  it's unit-tested; only load()/dump() live in the system-python helper.
"""
import os
import re

# The remappable PHYSICAL buttons per device, each mapping the source capability a
# button emits to its silkscreen label. This is a per-device table, NOT derived from
# the daemon's Capabilities property, because:
#   - Capabilities is a SUPERSET with phantoms (the Go 2 lists LeftPaddle3/
#     RightPaddle3 that no physical button emits) — deriving from it showed ghosts;
#   - the SAME capability is a DIFFERENT physical button per device (LeftPaddle1 is
#     the Go 2's "Y1" but the Claw's "M2") — labels must be per-device;
#   - a capability's normalized name (RightStickTouch) rarely matches the silkscreen
#     label printed on the device (M1).
# ONLY the grip/paddle buttons are listed: system buttons (Guide/QuickAccess/
# QuickAccess2/Keyboard) are deliberately omitted — remapping them breaks Steam/QAM
# navigation. Each entry is (source_capability, silkscreen_label). Labels are the
# literal names printed on the device and are NOT translated. An unlisted device
# degrades to an empty button list — never invents a mapping.
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
    "legion_go_s": [
        ("LeftPaddle1", "Y1"), ("RightPaddle1", "Y2"),
    ],
    "msi_claw_8_ai_plus": [
        ("RightPaddle1", "M1"), ("LeftPaddle1", "M2"),
    ],
    "msi_claw_a8": [
        ("RightPaddle1", "M1"), ("LeftPaddle1", "M2"),
    ],
    "rog_ally": [
        ("LeftPaddle1", "M2"), ("RightPaddle1", "M1"),
    ],
    "rog_ally_x": [
        ("LeftPaddle1", "M2"), ("RightPaddle1", "M1"),
    ],
}

# InputPlumber changed the normalized Xbox Ally paddle capabilities between shipped
# versions. Pick the generation that best matches the live daemon; ties prefer the
# current names. This keeps one physical M1/M2 pair in the UI instead of exposing
# duplicate aliases when a transitional daemon advertises both generations.
DEVICE_BUTTON_VARIANTS = {
    "rog_xbox_ally": [
        [("LeftPaddle2", "M2"), ("RightPaddle2", "M1")],
        [("LeftPaddle1", "M2"), ("RightPaddle1", "M1")],
    ],
    "rog_xbox_ally_x": [
        [("LeftPaddle2", "M2"), ("RightPaddle2", "M1")],
        [("LeftPaddle1", "M2"), ("RightPaddle1", "M1")],
    ],
}

# Exact CompositeDevice.Name values published by InputPlumber's shipped device
# profiles. Selection must never fall back to "the first composite" when more than
# one exists: a docked/Bluetooth controller may otherwise receive handheld writes.
COMPOSITE_NAMES = {
    "legion_go": ("Lenovo Legion Go",),
    "legion_go_s": ("Lenovo Legion Go S",),
    "legion_go_2": ("Lenovo Legion Go 2",),
    "rog_ally": ("ASUS ROG Ally",),
    "rog_ally_x": ("ASUS ROG Ally X",),
    "rog_xbox_ally": ("ASUS ROG Xbox Ally",),
    "rog_xbox_ally_x": ("ASUS ROG Xbox Ally",),
    "msi_claw_8_ai_plus": ("MSI Claw 8 AI+ A2VM",),
    "msi_claw_a8": ("MSI Claw A8 BZ2EM",),
    "gpd_win_5": ("GPD Win5",),
}

_PROFILE_PROOFS = {
    "rog_ally": {
        "profile": "/usr/share/inputplumber/devices/50-rog_ally.yaml",
        "profile_name": "ASUS ROG Ally",
        "map": "/usr/share/inputplumber/capability_maps/ally_type1.yaml",
        "map_id": "aly1",
    },
    "rog_ally_x": {
        "profile": "/usr/share/inputplumber/devices/50-rog_ally_x.yaml",
        "profile_name": "ASUS ROG Ally X",
        "map": "/usr/share/inputplumber/capability_maps/ally_type1.yaml",
        "map_id": "aly1",
    },
}

_ALLY_PADDLE_MAP = {
    "LeftPaddle1": ("KeyF14", 184),
    "RightPaddle1": ("KeyF15", 185),
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

MODIFIER_KEYS = (
    "KeyLeftCtrl", "KeyRightCtrl", "KeyLeftShift", "KeyRightShift",
    "KeyLeftAlt", "KeyRightAlt", "KeyLeftMeta", "KeyRightMeta",
)
KEY_TARGETS = (
    *MODIFIER_KEYS,
    "KeyEsc", "KeyEnter", "KeySpace", "KeyTab", "KeyBackspace",
    "KeyHome", "KeyEnd", "KeyPageUp", "KeyPageDown",
    "KeyUp", "KeyDown", "KeyLeft", "KeyRight", "KeyInsert", "KeyDelete",
    *(f"Key{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    *(f"Key{digit}" for digit in "1234567890"),
    *(f"KeyF{number}" for number in range(1, 25)),
    "KeyVolumeUp", "KeyVolumeDown", "KeyMute",
    "KeyBrightnessUp", "KeyBrightnessDown",
)


def _capability_names(capabilities) -> set:
    """Short names ('RightPaddle1') of the live capability strings
    ('Gamepad:Button:RightPaddle1')."""
    return {
        cap.rsplit(":", 1)[-1]
        for cap in (capabilities or [])
        if isinstance(cap, str)
    }


def _read_text(root, absolute):
    try:
        with open(os.path.join(root, absolute.lstrip("/"))) as file:
            return file.read()
    except OSError:
        return None


def _bitmap_bits(raw):
    try:
        words = [int(word, 16) for word in raw.split()]
    except (AttributeError, ValueError):
        return 0
    bits = 0
    for index, word in enumerate(reversed(words)):
        bits |= word << (index * 64)
    return bits


def _mapping_declared(mapping, source, target):
    pattern = (
        rf"(?m)^\s*source_events:\s*$\n"
        rf"\s*-\s*keyboard:\s*{re.escape(source)}\s*$\n"
        rf"\s*target_event:\s*$\n"
        rf"\s*gamepad:\s*$\n"
        rf"\s*button:\s*{re.escape(target)}\s*$"
    )
    return re.search(pattern, mapping) is not None


def proven_mapped_capabilities(device_key, source_paths, root="/") -> set:
    """Capabilities omitted by CompositeDevice but proven by the installed map.

    InputPlumber 0.78 maps the Ally's raw F14/F15 keys to paddle capabilities,
    yet does not list those mapped targets in CompositeDevice.Capabilities. Both
    the exact installed profile/map and the raw evdev key bit must agree before a
    paddle is surfaced.
    """
    proof = _PROFILE_PROOFS.get(device_key or "")
    if proof is None:
        return set()
    profile = _read_text(root, proof["profile"])
    mapping = _read_text(root, proof["map"])
    if profile is None or mapping is None:
        return set()
    if re.search(
        rf"(?m)^name:\s*{re.escape(proof['profile_name'])}\s*$",
        profile,
    ) is None or re.search(
        rf"(?m)^capability_map_id:\s*{re.escape(proof['map_id'])}\s*$",
        profile,
    ) is None or re.search(
        rf"(?m)^id:\s*{re.escape(proof['map_id'])}\s*$", mapping
    ) is None:
        return set()

    raw_bits = 0
    for source_path in source_paths or []:
        event = os.path.basename(source_path)
        if re.fullmatch(r"event\d+", event) is None:
            continue
        raw = _read_text(
            root, f"/sys/class/input/{event}/device/capabilities/key"
        )
        raw_bits |= _bitmap_bits(raw)

    return {
        target
        for target, (source, code) in _ALLY_PADDLE_MAP.items()
        if raw_bits & (1 << code)
        and _mapping_declared(mapping, source, target)
    }


def needs_mapped_capability_proof(device_key) -> bool:
    return (device_key or "") in _PROFILE_PROOFS


def buttons_for(device_key, capabilities, proven_capabilities=()) -> list:
    """The remappable physical buttons for this device as [(capability, silkscreen)],
    in display order. The per-device table is the source of truth for which buttons
    and what to call them; it's intersected with the LIVE capability set so we only
    surface a button the daemon actually reports (defensive — never invent one). An
    unknown device (not in the table) yields an empty list."""
    key = device_key or ""
    have = _capability_names(capabilities) | set(
        proven_capabilities or ()
    )
    variants = DEVICE_BUTTON_VARIANTS.get(key)
    entries = DEVICE_BUTTONS.get(key, [])
    if variants:
        entries = max(
            variants,
            key=lambda variant: sum(cap in have for cap, _label in variant),
        )
    return [
        (cap, label)
        for (cap, label) in entries
        if cap in have
    ]


def is_known_device(device_key) -> bool:
    """Whether we have a known button map for this device."""
    return device_key in DEVICE_BUTTONS or device_key in DEVICE_BUTTON_VARIANTS


def composite_names_for(device_key) -> tuple:
    return COMPOSITE_NAMES.get(device_key or "", ())


def sanitize_target(target: dict):
    """Coerce one target to {"gamepad"|"key": name}, or None if invalid."""
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


def sanitize_button_action(targets) -> list:
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= 4:
        return []
    clean = sanitize_targets(targets)
    if len(clean) != len(targets):
        return []
    if len(clean) == 1 and "gamepad" in clean[0]:
        return clean
    if not all("key" in target for target in clean):
        return []
    keys = [target["key"] for target in clean]
    if len(keys) != len(set(keys)):
        return []
    modifier_order = {
        key: index for index, key in enumerate(MODIFIER_KEYS)
    }
    modifiers = sorted(
        (key for key in keys if key in modifier_order),
        key=modifier_order.__getitem__,
    )
    main = [key for key in keys if key not in modifier_order]
    return [{"key": key} for key in (*modifiers, *main)]


def is_keyboard_chord(targets) -> bool:
    clean = sanitize_button_action(targets)
    return bool(clean) and all("key" in target for target in clean)


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


def apply_overrides_to_profile(profile: dict, overrides: dict) -> dict | None:
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
        matches = [entry for entry in mapping if source_button(entry) == button]
        if len(matches) > 1:
            return None
        clean = sanitize_button_action(targets)
        mapping = [e for e in mapping if source_button(e) != button]  # drop old
        if clean:
            mapping.append(_mapping_entry(button, clean))
    prof["mapping"] = mapping
    return prof
