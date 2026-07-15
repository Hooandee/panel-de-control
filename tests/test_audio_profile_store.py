from audio.profile_store import AudioProfileStore


def test_save_list_get(tmp_path):
    s = AudioProfileStore(str(tmp_path / "p.json"))
    s.save("Peli", [3] * 10, 40)
    assert s.get("Peli") == {"gains": [3.0] * 10, "bass": 40}
    names = [p["name"] for p in s.list()]
    assert names == ["Peli"]


def test_overwrite_same_name(tmp_path):
    s = AudioProfileStore(str(tmp_path / "p.json"))
    s.save("Peli", [1] * 10, 0)
    s.save("Peli", [5] * 10, 60)
    assert s.get("Peli")["gains"] == [5.0] * 10
    assert len(s.list()) == 1


def test_empty_name_ignored(tmp_path):
    s = AudioProfileStore(str(tmp_path / "p.json"))
    s.save("   ", [3] * 10, 0)
    assert s.list() == []


def test_clamp_on_save(tmp_path):
    s = AudioProfileStore(str(tmp_path / "p.json"))
    s.save("X", [99] * 10, 999)
    assert s.get("X")["gains"][0] == 12.0
    assert s.get("X")["bass"] == 100


def test_delete(tmp_path):
    s = AudioProfileStore(str(tmp_path / "p.json"))
    s.save("A", [0] * 10, 0)
    s.delete("A")
    assert s.get("A") is None


def test_persists_and_robust_load(tmp_path):
    p = str(tmp_path / "p.json")
    AudioProfileStore(p).save("A", [2] * 10, 10)
    assert AudioProfileStore(p).get("A")["gains"] == [2.0] * 10
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert AudioProfileStore(str(bad)).list() == []
