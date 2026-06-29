import json

from tdp_profiles import ProfileStore


def _store(tmp_path, default=15):
    return ProfileStore(str(tmp_path / "tdp_profiles.json"), default_watts=default)


def test_global_default_when_empty(tmp_path):
    s = _store(tmp_path, default=15)
    eff = s.effective(None)
    assert eff["pl1"] == 15 and eff["pl2"] == 15 and eff["pl3"] == 15
    assert eff["watts"] == 15  # back-compat alias = pl1
    assert s.effective("1091500")["pl1"] == 15  # no game profile → global


def test_set_watts_is_flat(tmp_path):
    s = _store(tmp_path)
    s.set_watts("global", 12)
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (12, 12, 12)
    assert eff["watts"] == 12


def test_set_levels_stores_three(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 15, 25, 30)
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (15, 25, 30)
    assert eff["watts"] == 15


def test_create_game_copies_global_then_overrides(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 18, 20, 22)
    s.create_game_from_global("1091500")
    assert s.has_game("1091500")
    assert s.effective("1091500")["pl1"] == 18
    s.set_levels("game", 10, 12, 14, appid="1091500")
    assert s.effective("1091500")["pl3"] == 14
    assert s.effective(None)["pl1"] == 18  # global unchanged


def test_persists_and_lists(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    s1 = ProfileStore(path, default_watts=15)
    s1.set_levels("global", 20, 30, 35)
    s1.set_watts("game", 8, appid="42")
    s2 = ProfileStore(path, default_watts=15)
    assert s2.effective(None)["pl1"] == 20 and s2.effective(None)["pl3"] == 35
    assert s2.effective("42")["pl1"] == 8
    assert s2.list_games() == ["42"]


def test_migrates_old_watts_shape(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"watts": 22}, "games": {"7": {"watts": 9}}}, f)
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["pl1"] == 22 and s.effective(None)["pl2"] == 22
    assert s.effective("7")["pl1"] == 9
