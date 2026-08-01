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
    # Silkscreen (Y1/M1/…) -> source capability, GRIPS ONLY.
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


def test_buttons_msi_claw_a8_two_grips():
    caps = ["Gamepad:Button:South", "Gamepad:Button:LeftPaddle1",
            "Gamepad:Button:RightPaddle1", "Gamepad:Button:Guide"]
    assert ip.buttons_for("msi_claw_a8", caps) == [
        ("RightPaddle1", "M1"),
        ("LeftPaddle1", "M2"),
    ]


def test_buttons_legion_go_s_two_grips():
    caps = [
        "Gamepad:Button:South",
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
        "Gamepad:Button:QuickAccess",
    ]
    assert ip.buttons_for("legion_go_s", caps) == [
        ("LeftPaddle1", "Y1"),
        ("RightPaddle1", "Y2"),
    ]


def test_buttons_rog_xbox_ally_family_two_macro_buttons():
    caps = [
        "Gamepad:Button:South",
        "Gamepad:Button:LeftPaddle2",
        "Gamepad:Button:RightPaddle2",
        "Gamepad:Button:QuickAccess",
    ]
    expected = [
        ("LeftPaddle2", "M2"),
        ("RightPaddle2", "M1"),
    ]
    assert ip.buttons_for("rog_xbox_ally", caps) == expected
    assert ip.buttons_for("rog_xbox_ally_x", caps) == expected


def test_buttons_original_rog_ally_family_two_macro_buttons():
    caps = [
        "Gamepad:Button:South",
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
        "Gamepad:Button:QuickAccess",
    ]
    expected = [
        ("LeftPaddle1", "M2"),
        ("RightPaddle1", "M1"),
    ]
    assert ip.buttons_for("rog_ally", caps) == expected
    assert ip.buttons_for("rog_ally_x", caps) == expected


def test_ally_paddles_require_installed_map_and_raw_key_evidence(tmp_path):
    profile = tmp_path / "usr/share/inputplumber/devices/50-rog_ally.yaml"
    mapping = (
        tmp_path
        / "usr/share/inputplumber/capability_maps/ally_type1.yaml"
    )
    keys = tmp_path / "sys/class/input/event3/device/capabilities/key"
    profile.parent.mkdir(parents=True)
    mapping.parent.mkdir(parents=True)
    keys.parent.mkdir(parents=True)
    profile.write_text(
        "name: ASUS ROG Ally\ncapability_map_id: aly1\n"
    )
    mapping.write_text(
        "id: aly1\n"
        "mapping:\n"
        "  - name: Left Paddle\n"
        "    source_events:\n"
        "      - keyboard: KeyF14\n"
        "    target_event:\n"
        "      gamepad:\n"
        "        button: LeftPaddle1\n"
        "  - name: Right Paddle\n"
        "    source_events:\n"
        "      - keyboard: KeyF15\n"
        "    target_event:\n"
        "      gamepad:\n"
        "        button: RightPaddle1\n"
    )
    keys.write_text(f"{(1 << 184) | (1 << 185):x}\n")

    proven = ip.proven_mapped_capabilities(
        "rog_ally", ["/dev/input/event3"], root=str(tmp_path)
    )

    assert proven == {"LeftPaddle1", "RightPaddle1"}
    assert ip.buttons_for("rog_ally", [], proven) == [
        ("LeftPaddle1", "M2"),
        ("RightPaddle1", "M1"),
    ]


def test_ally_paddle_proof_rejects_map_or_raw_capability_mismatch(
    tmp_path,
):
    profile = tmp_path / "usr/share/inputplumber/devices/50-rog_ally.yaml"
    mapping = (
        tmp_path
        / "usr/share/inputplumber/capability_maps/ally_type1.yaml"
    )
    keys = tmp_path / "sys/class/input/event3/device/capabilities/key"
    profile.parent.mkdir(parents=True)
    mapping.parent.mkdir(parents=True)
    keys.parent.mkdir(parents=True)
    profile.write_text(
        "name: ASUS ROG Ally\ncapability_map_id: aly1\n"
    )
    mapping.write_text(
        "id: aly1\nsource_events:\n"
        "  - keyboard: KeyF14\ntarget_event:\n"
        "  gamepad:\n    button: Guide\n"
    )
    keys.write_text(f"{1 << 184:x}\n")

    assert ip.proven_mapped_capabilities(
        "rog_ally", ["/dev/input/event3"], root=str(tmp_path)
    ) == set()


def test_buttons_rog_xbox_ally_family_supports_legacy_paddle_capabilities():
    caps = [
        "Gamepad:Button:South",
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
        "Gamepad:Button:QuickAccess",
    ]
    expected = [
        ("LeftPaddle1", "M2"),
        ("RightPaddle1", "M1"),
    ]
    assert ip.buttons_for("rog_xbox_ally", caps) == expected
    assert ip.buttons_for("rog_xbox_ally_x", caps) == expected


def test_buttons_rog_xbox_ally_prefers_one_capability_generation():
    caps = [
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:RightPaddle1",
        "Gamepad:Button:LeftPaddle2",
        "Gamepad:Button:RightPaddle2",
    ]
    expected = [
        ("LeftPaddle2", "M2"),
        ("RightPaddle2", "M1"),
    ]
    assert ip.buttons_for("rog_xbox_ally_x", caps) == expected


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
    assert ip.is_known_device("msi_claw_a8") is True
    assert ip.is_known_device("legion_go_s") is True
    assert ip.is_known_device("rog_xbox_ally") is True
    assert ip.is_known_device("rog_xbox_ally_x") is True
    assert ip.is_known_device("rog_ally") is True
    assert ip.is_known_device("rog_ally_x") is True
    assert ip.is_known_device(None) is False


def test_expected_composite_names_are_exact_per_device():
    assert ip.composite_names_for("legion_go") == ("Lenovo Legion Go",)
    assert ip.composite_names_for("legion_go_s") == ("Lenovo Legion Go S",)
    assert ip.composite_names_for("rog_ally") == ("ASUS ROG Ally",)
    assert ip.composite_names_for("unknown") == ()


def test_sanitize_targets():
    assert ip.sanitize_target({"gamepad": "South"}) == {"gamepad": "South"}
    assert ip.sanitize_target({"key": "KeyEsc"}) == {"key": "KeyEsc"}
    assert ip.sanitize_target({"gamepad": "Bogus"}) is None
    assert ip.sanitize_targets([{"gamepad": "South"}, {"key": "bad"}]) == [{"gamepad": "South"}]


def test_ctrl_tab_is_a_valid_chord():
    assert ip.sanitize_button_action([
        {"key": "KeyLeftCtrl"}, {"key": "KeyTab"},
    ]) == [
        {"key": "KeyLeftCtrl"}, {"key": "KeyTab"},
    ]
    assert ip.is_keyboard_chord([
        {"key": "KeyLeftCtrl"}, {"key": "KeyTab"},
    ]) is True


def test_chord_canonicalizes_modifiers_before_main_keys():
    assert ip.sanitize_button_action([
        {"key": "KeyTab"}, {"key": "KeyLeftShift"},
        {"key": "KeyLeftCtrl"},
    ]) == [
        {"key": "KeyLeftCtrl"}, {"key": "KeyLeftShift"},
        {"key": "KeyTab"},
    ]


def test_mixed_duplicate_unsafe_and_oversized_actions_are_rejected():
    assert ip.sanitize_button_action([
        {"gamepad": "South"}, {"key": "KeyTab"},
    ]) == []
    assert ip.sanitize_button_action([
        {"key": "KeyTab"}, {"key": "KeyTab"},
    ]) == []
    assert ip.sanitize_button_action([{"key": "KeyPower"}]) == []
    assert ip.sanitize_button_action([{"key": "KeySysrq"}]) == []
    assert ip.sanitize_button_action([
        {"key": "KeyLeftCtrl"}, {"key": "KeyLeftShift"},
        {"key": "KeyLeftAlt"}, {"key": "KeyLeftMeta"},
        {"key": "KeyTab"},
    ]) == []


def test_curated_chord_catalog_includes_letters_digits_navigation_and_f_keys():
    for key in ("KeyA", "Key7", "KeyHome", "KeyPageDown", "KeyF24"):
        assert ip.sanitize_button_action([{"key": key}]) == [{"key": key}]


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
