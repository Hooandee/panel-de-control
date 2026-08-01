import json

from controllers.store import RemapStore


def _store(tmp_path, data=None):
    p = tmp_path / "remap.json"
    if data is not None:
        p.write_text(json.dumps(data))
    return RemapStore(str(p))


def test_migrates_old_flat_shape_into_global(tmp_path):
    s = _store(tmp_path, {"LeftPaddle1": [{"gamepad": "South"}]})
    assert s.overrides_for("global") == {"LeftPaddle1": [{"gamepad": "South"}]}
    assert s.list_games() == []


def test_no_game_follows_global(tmp_path):
    s = _store(tmp_path, {"A": [{"gamepad": "South"}]})
    assert s.is_following_global(None) is True
    assert s.is_following_global("42") is True  # unknown game → global
    assert s.effective_overrides("42") == {"A": [{"gamepad": "South"}]}
    assert s.effective_vibration("42") == {}


def test_game_profile_is_independent_and_survives_follow_toggle(tmp_path):
    s = _store(tmp_path, {"A": [{"gamepad": "South"}]})
    s.replace("game", "7", {"B": [{"gamepad": "North"}]})
    assert s.has_game("7") is True
    assert s.is_following_global("7") is False
    assert s.effective_overrides("7") == {"B": [{"gamepad": "North"}]}
    # Follow global: the game's own overrides are NOT deleted, just deactivated.
    s.set_follow_global("7", True)
    assert s.is_following_global("7") is True
    assert s.effective_overrides("7") == {"A": [{"gamepad": "South"}]}  # global now
    assert s.overrides_for("game", "7") == {"B": [{"gamepad": "North"}]}  # still stored
    # Back to its own.
    s.set_follow_global("7", False)
    assert s.effective_overrides("7") == {"B": [{"gamepad": "North"}]}


def test_create_game_from_global_seeds_and_persists(tmp_path):
    p = tmp_path / "remap.json"
    p.write_text(json.dumps({"A": [{"gamepad": "South"}]}))
    s = RemapStore(str(p))
    s.create_game_from_global("9")
    assert s.overrides_for("game", "9") == {"A": [{"gamepad": "South"}]}
    # Reloaded from disk → the game profile persisted with its flag.
    s2 = RemapStore(str(p))
    assert s2.has_game("9") is True
    assert s2.is_following_global("9") is False


def test_vibration_is_scoped_with_buttons_and_persists(tmp_path):
    p = tmp_path / "remap.json"
    s = RemapStore(str(p))
    s.patch_vibration("global", None, {"enabled": False})
    assert s.effective_vibration("42") == {"enabled": False}

    s.create_game_from_global("42")
    s.patch_vibration("game", "42", {"enabled": True})
    assert s.effective_vibration("42") == {"enabled": True}
    assert s.effective_profile("42") == {
        "buttons": {},
        "vibration": {"enabled": True},
        "virtual_controller": {},
    }

    s2 = RemapStore(str(p))
    assert s2.vibration_for("global") == {"enabled": False}
    assert s2.vibration_for("game", "42") == {"enabled": True}


def test_vibration_preserves_persistent_intensity_fields(tmp_path):
    p = tmp_path / "remap.json"
    s = RemapStore(str(p))
    s.patch_vibration(
        "game", "42", {"enabled": True, "left": 35, "right": 45}
    )

    assert RemapStore(str(p)).effective_vibration("42") == {
        "enabled": True,
        "left": 35,
        "right": 45,
    }


def test_game_difference_includes_vibration(tmp_path):
    s = _store(tmp_path)
    s.patch_vibration("global", None, {"enabled": True})
    s.create_game_from_global("7")
    assert s.differs_from_global("7") is False
    s.patch_vibration("game", "7", {"enabled": False})
    assert s.differs_from_global("7") is True


def test_profile_ownership_state_is_per_device_and_persists(tmp_path):
    p = tmp_path / "remap.json"
    s = RemapStore(str(p))
    s.remember_profile_baseline("rog_ally", "baseline")
    s.remember_applied_profile("rog_ally", "applied")
    assert s.profile_state("legion_go") is None

    s2 = RemapStore(str(p))
    assert s2.profile_state("rog_ally") == {
        "baseline_yaml": "baseline",
        "last_applied_yaml": "applied",
    }
    s2.forget_profile_state("rog_ally")
    assert s2.profile_state("rog_ally") is None


def test_corrupt_profile_recovery_shape_degrades_to_empty(tmp_path):
    import json

    path = tmp_path / "remap.json"
    path.write_text(json.dumps({
        "global": {},
        "games": {},
        "profile_states": {
            "legion_go": {
                "baseline_yaml": "baseline",
                "recovery_yamls": 42,
            }
        },
    }))

    store = RemapStore(str(path))

    assert store.profile_state("legion_go") == {
        "baseline_yaml": "baseline",
        "last_applied_yaml": None,
    }


def test_non_finite_vibration_value_degrades_to_empty(tmp_path):
    path = tmp_path / "remap.json"
    path.write_text(
        '{"global":{},"games":{},"vibration":{"value":NaN}}'
    )

    store = RemapStore(str(path))

    assert store.vibration_for("global") == {}


def test_vibration_baseline_is_isolated_per_owner_and_device(tmp_path):
    store = RemapStore(str(tmp_path / "remap.json"))
    store.remember_vibration_baseline(
        "hhd:rog_ally", {"enabled": True, "value": 80}
    )
    store.remember_vibration_baseline(
        "inputplumber:legion_go",
        {"enabled": False, "value": 100},
    )

    assert store.vibration_baseline("hhd:rog_ally") == {
        "enabled": True, "value": 80,
    }
    assert store.vibration_baseline("inputplumber:legion_go") == {
        "enabled": False, "value": 100,
    }


def test_vibration_baseline_preserves_exact_native_motor_values(tmp_path):
    path = tmp_path / "remap.json"
    store = RemapStore(str(path))
    store.remember_vibration_baseline(
        "inputplumber:rog_ally",
        {"enabled": True, "native_left": 1, "native_right": 63},
    )

    reloaded = RemapStore(str(path))
    assert reloaded.vibration_baseline("inputplumber:rog_ally") == {
        "enabled": True,
        "native_left": 1,
        "native_right": 63,
    }


def test_existing_percentage_baseline_is_not_enriched_from_live_native_state(
    tmp_path,
):
    store = RemapStore(str(tmp_path / "remap.json"))
    store.remember_vibration_baseline(
        "inputplumber:rog_ally",
        {"enabled": True, "left": 20, "right": 80},
    )

    store.remember_vibration_baseline(
        "inputplumber:rog_ally",
        {"native_left": 22, "native_right": 29},
    )

    assert store.vibration_baseline("inputplumber:rog_ally") == {
        "enabled": True,
        "left": 20,
        "right": 80,
    }


def test_corrupt_load_is_empty(tmp_path):
    p = tmp_path / "remap.json"
    p.write_text("{ not json")
    s = RemapStore(str(p))
    assert s.overrides_for("global") == {}
    assert s.list_games() == []


def test_game_profile_and_forget(tmp_path):
    s = _store(tmp_path)
    assert s.game_profile("7") is None
    s.replace("game", "7", {"B": [{"gamepad": "North"}]})
    assert s.game_profile("7") == {"B": [{"gamepad": "North"}]}
    s.forget_game("7")
    assert s.has_game("7") is False
    assert s.game_profile("7") is None


def test_v2_migrates_without_losing_buttons_or_vibration(tmp_path):
    store = _store(tmp_path, {
        "global": {
            "LeftPaddle1": [{"gamepad": "South"}],
        },
        "vibration": {"left": 35, "right": 45},
        "games": {
            "42": {
                "overrides": {"RightPaddle1": [{"key": "KeyTab"}]},
                "vibration": {"left": 20},
                "follow_global": False,
            },
        },
    })

    assert store.effective_profile(None) == {
        "buttons": {"LeftPaddle1": [{"gamepad": "South"}]},
        "vibration": {"left": 35, "right": 45},
        "virtual_controller": {},
    }
    assert store.effective_profile("42") == {
        "buttons": {"RightPaddle1": [{"key": "KeyTab"}]},
        "vibration": {"left": 20},
        "virtual_controller": {},
    }


def test_version_three_deeply_cleans_button_actions(tmp_path):
    store = _store(tmp_path, {
        "version": 3,
        "global": {
            "buttons": {
                "valid_gamepad": [{"gamepad": "South"}],
                "valid_chord": [{"key": "KeyLeftCtrl"}, {"key": "KeyTab"}],
                "mixed": [{"gamepad": "South"}, {"key": "KeyTab"}],
                "duplicate": [{"key": "KeyTab"}, {"key": "KeyTab"}],
                "nested": [{"key": ["KeyTab"]}],
                "too_long": [
                    {"key": "KeyLeftCtrl"}, {"key": "KeyLeftShift"},
                    {"key": "KeyLeftAlt"}, {"key": "KeyTab"},
                    {"key": "KeyEnter"},
                ],
            },
            "vibration": {},
            "virtual_controller": {},
        },
    })

    assert store.effective_overrides(None) == {
        "valid_gamepad": [{"gamepad": "South"}],
        "valid_chord": [{"key": "KeyLeftCtrl"}, {"key": "KeyTab"}],
    }


def test_component_profiles_are_independent_and_resettable(tmp_path):
    store = _store(tmp_path)
    store.patch_component(
        "virtual_controller", {"mode": "xbox_elite"}, "global", None
    )
    store.create_game_from_global("42")
    store.patch_component(
        "virtual_controller", {"mode": "dualsense"}, "game", "42"
    )
    store.patch_component("vibration", {"left": 20}, "game", "42")

    assert store.effective_profile("42")["virtual_controller"] == {
        "mode": "dualsense",
    }
    assert store.differs_from_global("42", "virtual_controller") is True
    assert store.differs_from_global("42", "buttons") is False

    store.reset_component("virtual_controller", "game", "42")
    assert store.effective_profile("42")["virtual_controller"] == {}
    assert store.effective_profile("42")["vibration"] == {"left": 20}


def test_virtual_mode_rejects_unknown_shape(tmp_path):
    store = _store(tmp_path, {
        "version": 3,
        "global": {
            "buttons": {},
            "vibration": {},
            "virtual_controller": {"mode": "Bad mode!", "extra": True},
        },
    })

    assert store.effective_profile(None)["virtual_controller"] == {}


def test_invalid_native_baseline_pair_is_discarded_not_clamped(tmp_path):
    path = tmp_path / "remap.json"
    store = RemapStore(str(path))
    store.remember_vibration_baseline(
        "inputplumber:rog_ally",
        {"native_left": 65, "native_right": 10},
    )

    assert RemapStore(str(path)).vibration_baseline(
        "inputplumber:rog_ally"
    ) == {}
