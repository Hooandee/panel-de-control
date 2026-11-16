from mangohud.config import DEFAULT_MODEL
from mangohud.store import HudStore


def test_load_missing_file_returns_defaults(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    assert store.load() == DEFAULT_MODEL


def _items(*ids):
    return [{"kind": "metric", "id": i} for i in ids]


def test_save_then_load_roundtrips(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    store.save({"items": _items("fps", "gpu"), "position": "bottom-right", "enabled": True})
    got = store.load()
    assert got["items"] == _items("fps", "gpu")
    assert got["position"] == "bottom-right"
    assert got["enabled"] is True


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "hud.json"
    path.write_text("{ this is not json")
    assert HudStore(str(path)).load() == DEFAULT_MODEL


def test_save_normalizes_before_persisting(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    store.save({"items": _items("fps", "bogus", "fps"), "position": "middle"})
    got = store.load()
    assert got["items"] == _items("fps")  # unknown dropped, deduped
    assert got["position"] == "top-left"  # invalid fell back


def _write(path, data):
    import json

    path.write_text(json.dumps(data))


def test_flat_legacy_file_loads_as_the_global_model(tmp_path):
    path = tmp_path / "hud.json"
    _write(path, {"enabled": True, "items": _items("fps", "gpu"), "position": "bottom-right"})
    store = HudStore(str(path))
    assert store.load()["items"] == _items("fps", "gpu")
    assert store.load()["enabled"] is True
    assert store.list_games() == []
    # a game that never configured anything follows the global model
    assert store.effective("42") == store.load()


def test_file_stays_flat_until_a_game_has_its_own_model(tmp_path):
    import json

    path = tmp_path / "hud.json"
    store = HudStore(str(path))
    store.save({"enabled": True, "items": _items("fps")})
    assert "global" not in json.loads(path.read_text())
    assert json.loads(path.read_text())["enabled"] is True

    store.set_model("game", "42", {"enabled": True, "items": _items("cpu")})
    stored = json.loads(path.read_text())
    assert set(stored) == {"global", "games"}
    assert stored["games"]["42"]["items"] == _items("cpu")

    store.forget_game("42")
    assert "games" not in json.loads(path.read_text())


def test_game_with_own_model_applies_it_and_others_follow_global(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    store.save({"enabled": False, "items": _items("fps")})
    store.set_model("game", "A", {"enabled": True, "items": _items("cpu")})
    assert store.effective("A")["enabled"] is True
    assert store.effective("A")["items"] == _items("cpu")
    assert store.effective("B")["enabled"] is False
    assert store.effective(None)["enabled"] is False


def test_follow_global_keeps_the_own_model(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    store.save({"enabled": False, "items": _items("fps")})
    store.set_model("game", "A", {"enabled": True, "items": _items("cpu")})
    store.set_follow("A", True)
    assert store.effective("A")["enabled"] is False
    assert store.own_hud_games() == []
    store.set_follow("A", False)
    assert store.effective("A")["items"] == _items("cpu")
    assert store.own_hud_games() == ["A"]


def test_using_own_hud_the_first_time_seeds_it_from_global(tmp_path):
    store = HudStore(str(tmp_path / "hud.json"))
    store.save({"enabled": True, "items": _items("fps", "ram")})
    store.set_follow("A", False)
    assert store.effective("A") == store.load()
    store.set_model("game", "A", {"enabled": False, "items": _items("fps", "ram")})
    assert store.load()["enabled"] is True


def test_scoped_file_roundtrips_and_cleans_game_models(tmp_path):
    path = tmp_path / "hud.json"
    store = HudStore(str(path))
    store.set_model("game", "A", {"enabled": True, "items": _items("fps", "bogus"), "position": "x"})
    again = HudStore(str(path))
    assert again.effective("A")["items"] == _items("fps")
    assert again.effective("A")["position"] == "top-left"
    assert again.is_following_global("A") is False
