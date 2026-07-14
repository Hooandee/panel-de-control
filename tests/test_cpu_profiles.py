from cpu.profiles import CpuProfileStore


def _store(tmp_path):
    return CpuProfileStore(str(tmp_path / "cpu_profiles.json"))


def test_defaults(tmp_path):
    e = _store(tmp_path).effective(None)
    assert e == {"smt": True, "boost": True, "cores": None}


def test_per_game_overrides_global(tmp_path):
    s = _store(tmp_path)
    s.set_boost("global", True)
    s.set_boost("game", False, appid="42")
    s.set_cores("game", 4, appid="42")
    assert s.effective("42") == {"smt": True, "boost": False, "cores": 4}
    assert s.effective(None)["boost"] is True   # global untouched


def test_follow_global_keeps_own(tmp_path):
    s = _store(tmp_path)
    s.set_smt("global", True)
    s.set_smt("game", False, appid="42")
    assert s.effective("42")["smt"] is False
    s.set_follow_global("42", True)
    assert s.effective("42")["smt"] is True      # global applied
    assert s.has_game("42") and s.is_following_global("42") is True
    s.set_follow_global("42", False)
    assert s.effective("42")["smt"] is False      # own restored, never lost


def test_game_without_profile_follows_global(tmp_path):
    assert _store(tmp_path).is_following_global("999") is True


def test_new_game_profile_inherits_global(tmp_path):
    s = _store(tmp_path)
    s.set_smt("global", False)
    s.set_boost("global", False)
    s.set_cores("game", 4, appid="42")  # first write to this game
    assert s.effective("42") == {"smt": False, "boost": False, "cores": 4}


def test_persists(tmp_path):
    path = str(tmp_path / "c.json")
    s1 = CpuProfileStore(path)
    s1.set_cores("game", 6, appid="42")
    s1.set_follow_global("42", True)
    s2 = CpuProfileStore(path)
    assert s2.effective("42") == {"smt": True, "boost": True, "cores": None}  # follows global
    assert s2.is_following_global("42") is True
    s2.set_follow_global("42", False)
    assert s2.effective("42")["cores"] == 6      # own value survived reload


def test_game_profile_returns_own_values_without_follow_flag(tmp_path):
    s = _store(tmp_path)
    assert s.game_profile("42") is None
    s.set_smt("game", False, appid="42")
    prof = s.game_profile("42")
    assert prof["smt"] is False and "follow_global" not in prof


def test_forget_game_reverts_to_global(tmp_path):
    s = _store(tmp_path)
    s.set_smt("game", False, appid="42")
    assert s.has_game("42") is True
    s.forget_game("42")
    assert s.has_game("42") is False
    assert s.game_profile("42") is None
    assert s.effective("42") == s.effective(None)  # back to global


def test_differs_from_global(tmp_path):
    s = _store(tmp_path)
    assert s.differs_from_global("42") is False          # no own profile
    s.create_game_from_global("42")                       # bare scope-toggle: copies global
    assert s.differs_from_global("42") is False          # same as global → not configured
    s.set_smt("game", False, appid="42")                 # actually change something
    assert s.differs_from_global("42") is True
