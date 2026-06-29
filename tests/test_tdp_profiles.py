from tdp_profiles import ProfileStore


def _store(tmp_path, default=15):
    return ProfileStore(str(tmp_path / "tdp_profiles.json"), default_watts=default)


def test_global_default_when_empty(tmp_path):
    s = _store(tmp_path, default=15)
    assert s.effective(None) == {"watts": 15}
    assert s.effective("1091500") == {"watts": 15}  # no game profile → global


def test_set_global_watts(tmp_path):
    s = _store(tmp_path)
    s.set_watts("global", 12)
    assert s.effective(None) == {"watts": 12}


def test_create_game_copies_global_then_overrides(tmp_path):
    s = _store(tmp_path)
    s.set_watts("global", 18)
    s.create_game_from_global("1091500")
    assert s.has_game("1091500") is True
    assert s.effective("1091500") == {"watts": 18}  # copied from global
    s.set_watts("game", 10, appid="1091500")
    assert s.effective("1091500") == {"watts": 10}   # game override
    assert s.effective(None) == {"watts": 18}         # global unchanged


def test_persists_across_reload(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    s1 = ProfileStore(path, default_watts=15)
    s1.set_watts("global", 20)
    s1.set_watts("game", 8, appid="42")
    s2 = ProfileStore(path, default_watts=15)
    assert s2.effective(None) == {"watts": 20}
    assert s2.effective("42") == {"watts": 8}
    assert s2.list_games() == ["42"]


def test_set_watts_on_missing_game_creates_it(tmp_path):
    s = _store(tmp_path)
    s.set_watts("game", 9, appid="777")
    assert s.has_game("777") and s.effective("777") == {"watts": 9}
