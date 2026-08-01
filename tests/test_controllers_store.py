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
