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


def test_corrupt_load_is_empty(tmp_path):
    p = tmp_path / "remap.json"
    p.write_text("{ not json")
    s = RemapStore(str(p))
    assert s.overrides_for("global") == {}
    assert s.list_games() == []
