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
