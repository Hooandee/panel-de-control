import json

from cpu.profiles import CpuProfileStore


AUTO_FREQUENCY = {"manual": False, "min_khz": None, "max_khz": None}


def _profile(smt=True, boost=True, cores=None, frequency=None):
    return {
        "smt": smt,
        "boost": boost,
        "cores": cores,
        "frequency": frequency or dict(AUTO_FREQUENCY),
    }


def _store(tmp_path):
    return CpuProfileStore(str(tmp_path / "cpu_profiles.json"))


def test_defaults(tmp_path):
    e = _store(tmp_path).effective(None)
    assert e == _profile()


def test_per_game_overrides_global(tmp_path):
    s = _store(tmp_path)
    s.set_boost("global", True)
    s.set_boost("game", False, appid="42")
    s.set_cores("game", 4, appid="42")
    assert s.effective("42") == _profile(boost=False, cores=4)
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
    assert s.effective("42") == _profile(smt=False, boost=False, cores=4)


def test_persists(tmp_path):
    path = str(tmp_path / "c.json")
    s1 = CpuProfileStore(path)
    s1.set_cores("game", 6, appid="42")
    s1.set_follow_global("42", True)
    s2 = CpuProfileStore(path)
    assert s2.effective("42") == _profile()
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


def test_old_profile_migrates_frequency_to_auto_without_losing_cpu_fields(tmp_path):
    path = tmp_path / "cpu_profiles.json"
    path.write_text(json.dumps({
        "global": {"smt": False, "boost": True, "cores": 6},
        "games": {"42": {"smt": True, "boost": False, "cores": 4}},
    }))

    store = CpuProfileStore(str(path))

    assert store.effective(None) == _profile(smt=False, boost=True, cores=6)
    assert store.effective("42") == _profile(smt=True, boost=False, cores=4)


def test_manual_frequency_round_trips_in_global_and_game_scopes(tmp_path):
    path = str(tmp_path / "cpu_profiles.json")
    store = CpuProfileStore(path)
    store.set_frequency("global", 600_000, 3_200_000)
    store.set_frequency("game", 1_200_000, 2_400_000, appid="42")

    reloaded = CpuProfileStore(path)

    assert reloaded.effective(None)["frequency"] == {
        "manual": True, "min_khz": 600_000, "max_khz": 3_200_000,
    }
    assert reloaded.effective("42")["frequency"] == {
        "manual": True, "min_khz": 1_200_000, "max_khz": 2_400_000,
    }
    reloaded.set_frequency_auto("game", appid="42")
    assert reloaded.effective("42")["frequency"] == AUTO_FREQUENCY


def test_follow_global_selects_one_coherent_frequency_profile(tmp_path):
    store = _store(tmp_path)
    store.set_frequency("global", 600_000, 3_200_000)
    store.set_frequency("game", 1_200_000, 2_400_000, appid="42")
    assert store.effective("42")["frequency"]["min_khz"] == 1_200_000

    store.set_follow_global("42", True)

    assert store.effective("42")["frequency"] == store.effective(None)["frequency"]
    assert store.game_profile("42")["frequency"]["min_khz"] == 1_200_000


def test_malformed_frequency_falls_back_to_auto_and_preserves_other_fields(tmp_path):
    path = tmp_path / "cpu_profiles.json"
    path.write_text(json.dumps({
        "global": {
            "smt": False,
            "boost": False,
            "cores": 4,
            "frequency": {"manual": True, "min_khz": True, "max_khz": 2_400_000},
        },
    }))

    effective = CpuProfileStore(str(path)).effective(None)

    assert effective == _profile(smt=False, boost=False, cores=4)


def test_crossed_frequency_window_is_cleaned_to_auto(tmp_path):
    path = tmp_path / "cpu_profiles.json"
    path.write_text(json.dumps({
        "global": {
            "frequency": {"manual": True, "min_khz": 2_600_000, "max_khz": 2_400_000},
        },
    }))

    assert CpuProfileStore(str(path)).effective(None)["frequency"] == AUTO_FREQUENCY
