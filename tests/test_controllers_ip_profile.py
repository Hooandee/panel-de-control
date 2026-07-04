from controllers import ip_profile as ip

# Full Legion Go 2 source capability set (superset — includes phantom paddles the
# device has no physical button for, and the system buttons we must NOT expose).
GO2_CAPS = [
    "Gamepad:Button:South", "Gamepad:Button:North", "Gamepad:Button:DPadUp",
    "Gamepad:Button:LeftPaddle1", "Gamepad:Button:LeftPaddle2",
    "Gamepad:Button:RightPaddle1", "Gamepad:Button:RightPaddle2",
    "Gamepad:Button:RightPaddle3",  # phantom on the Go 2 — no physical button
    "Gamepad:Button:LeftStickTouch", "Gamepad:Button:RightStickTouch",
    "Gamepad:Button:QuickAccess", "Gamepad:Button:QuickAccess2",
    "Gamepad:Button:Keyboard", "Gamepad:Button:Guide",
    "Gamepad:Axis:LeftStick",
]


def test_buttons_legion_go_2_silkscreen_map_grips_only():
    # Validated on-device: silkscreen (Y1/M1/…) -> source capability, GRIPS ONLY.
    # Phantoms (RightPaddle3) and system buttons (Guide/QuickAccess/…) are excluded.
    assert ip.buttons_for("legion_go_2", GO2_CAPS) == [
        ("LeftPaddle1", "Y1"),
        ("LeftPaddle2", "Y2"),
        ("RightPaddle1", "Y3"),
        ("RightStickTouch", "M1"),
        ("LeftStickTouch", "M2"),
        ("RightPaddle2", "M3"),
    ]


def test_buttons_legion_go_1_omits_unmapped_m1():
    # M1 on the Go 1 emits a mouse/keyboard event (not a gamepad cap) → not remappable.
    caps = [
        "Gamepad:Button:LeftPaddle1", "Gamepad:Button:LeftPaddle2",
        "Gamepad:Button:RightPaddle1", "Gamepad:Button:RightPaddle2",
        "Gamepad:Button:LeftStickTouch", "Gamepad:Button:Guide",
    ]
    assert ip.buttons_for("legion_go", caps) == [
        ("LeftPaddle1", "Y1"),
        ("LeftPaddle2", "Y2"),
        ("RightPaddle1", "Y3"),
        ("LeftStickTouch", "M2"),
        ("RightPaddle2", "M3"),
    ]


def test_buttons_msi_claw_two_grips():
    caps = ["Gamepad:Button:South", "Gamepad:Button:LeftPaddle1",
            "Gamepad:Button:RightPaddle1", "Gamepad:Button:Guide"]
    # Same caps as a Legion Y1/Y3 but on the Claw they are the physical M1/M2.
    assert ip.buttons_for("msi_claw_8_ai_plus", caps) == [
        ("RightPaddle1", "M1"),
        ("LeftPaddle1", "M2"),
    ]


def test_buttons_defensively_intersect_live_capabilities():
    # A known device that (for whatever reason) doesn't report a capability →
    # that button is omitted, never invented.
    caps = ["Gamepad:Button:LeftPaddle1", "Gamepad:Button:RightPaddle1"]
    assert ip.buttons_for("legion_go_2", caps) == [
        ("LeftPaddle1", "Y1"),
        ("RightPaddle1", "Y3"),
    ]


def test_buttons_unknown_device_is_empty():
    assert ip.buttons_for("some_new_handheld", GO2_CAPS) == []
    assert ip.buttons_for(None, GO2_CAPS) == []
    assert ip.buttons_for("legion_go_2", []) == []
    assert ip.buttons_for("legion_go_2", None) == []


def test_is_known_device():
    assert ip.is_known_device("legion_go_2") is True
    assert ip.is_known_device("msi_claw_8_ai_plus") is True
    assert ip.is_known_device("legion_go_s") is False  # not validated on-device
    assert ip.is_known_device(None) is False


def test_sanitize_targets():
    assert ip.sanitize_target({"gamepad": "South"}) == {"gamepad": "South"}
    assert ip.sanitize_target({"key": "KeyEsc"}) == {"key": "KeyEsc"}
    assert ip.sanitize_target({"gamepad": "Bogus"}) is None
    assert ip.sanitize_targets([{"gamepad": "South"}, {"key": "bad"}]) == [{"gamepad": "South"}]


def test_apply_override_replaces_only_that_button_and_preserves_the_rest():
    profile = {
        "version": 1,
        "kind": "DeviceProfile",
        "name": "Default",
        "mapping": [
            {"name": "LeftPaddle1", "source_event": {"gamepad": {"button": "LeftPaddle1"}},
             "target_events": [{"gamepad": {"button": "LeftPaddle1"}}]},
            # A dial mapping must be preserved untouched.
            {"name": "Left Dial clockwise",
             "source_event": {"gamepad": {"dial": {"name": "LeftStickDial", "direction": "clockwise"}}},
             "target_events": [{"keyboard": "KeyVolumeUp"}]},
        ],
    }
    out = ip.apply_overrides_to_profile(profile, {"LeftPaddle1": [{"gamepad": "South"}]})
    entries = {m["name"]: m for m in out["mapping"]}
    # Dial preserved.
    assert entries["Left Dial clockwise"]["target_events"] == [{"keyboard": "KeyVolumeUp"}]
    # Paddle retargeted.
    lp = next(m for m in out["mapping"] if m["source_event"]["gamepad"].get("button") == "LeftPaddle1")
    assert lp["target_events"] == [{"gamepad": {"button": "South"}}]
    # Original profile not mutated.
    assert profile["mapping"][0]["target_events"] == [{"gamepad": {"button": "LeftPaddle1"}}]


def test_apply_override_to_keyboard_key():
    out = ip.apply_overrides_to_profile({"mapping": []}, {"RightPaddle1": [{"key": "KeyEsc"}]})
    assert out["mapping"] == [{
        "name": "RightPaddle1",
        "source_event": {"gamepad": {"button": "RightPaddle1"}},
        "target_events": [{"keyboard": "KeyEsc"}],
    }]


def test_apply_empty_override_reverts_button_to_default():
    profile = {"mapping": [
        {"name": "LeftPaddle1", "source_event": {"gamepad": {"button": "LeftPaddle1"}},
         "target_events": [{"gamepad": {"button": "South"}}]},
    ]}
    out = ip.apply_overrides_to_profile(profile, {"LeftPaddle1": [{"key": "bad"}]})
    # No valid target → our entry is dropped so the daemon's default takes over.
    assert out["mapping"] == []
