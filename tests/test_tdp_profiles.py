import json

from tdp_profiles import ProfileStore


def _store(tmp_path, default=15):
    return ProfileStore(str(tmp_path / "tdp_profiles.json"), default_watts=default)


def test_global_default_is_auto_and_derives(tmp_path):
    s = _store(tmp_path, default=15)
    eff = s.effective(None)
    assert eff["pl1"] == 15
    assert eff["pl2"] == 18 and eff["pl3"] == 21  # 1.2x / 1.4x derived
    assert eff["auto"] is True
    assert eff["watts"] == 15  # back-compat alias = pl1
    assert s.effective("1091500")["pl1"] == 15  # no game profile -> global


def test_set_pl1_keeps_auto_and_redrives(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 12)
    eff = s.effective(None)
    assert eff["pl1"] == 12 and eff["pl2"] == 14 and eff["pl3"] == 17  # round(14.4)/round(16.8)
    assert eff["auto"] is True


def test_set_offsets_goes_manual(tmp_path):
    s = _store(tmp_path)  # default pl1=15
    s.set_offsets("global", 8, 4)
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (15, 23, 27)
    assert eff["auto"] is False


def test_set_levels_absolute_api_stores_offsets(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 15, 25, 30)  # absolute API -> off2=10, off3=5
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (15, 25, 30)
    assert eff["auto"] is False


def test_set_pl1_preserves_margins_no_bounce(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 17)
    s.set_offsets("global", 20, 10)
    assert s.effective(None)["pl2"] == 37 and s.effective(None)["pl3"] == 47
    s.set_pl1("global", 35)  # raise PL1: margins preserved (unclamped intent)
    assert s.effective(None)["pl2"] == 55 and s.effective(None)["pl3"] == 65
    s.set_pl1("global", 17)  # lower again: margins fully restored, no shrink
    assert s.effective(None)["pl2"] == 37 and s.effective(None)["pl3"] == 47


def test_set_auto_reverts_to_derived(tmp_path):
    s = _store(tmp_path)
    s.set_offsets("global", 8, 4)
    assert s.effective(None)["auto"] is False
    s.set_auto("global")
    eff = s.effective(None)
    assert eff["auto"] is True and eff["pl2"] == 18  # back to derived


def test_create_game_copies_global_then_overrides(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 18, 20, 22)
    s.create_game_from_global("1091500")
    assert s.has_game("1091500")
    assert s.effective("1091500")["pl1"] == 18 and s.effective("1091500")["pl2"] == 20
    s.set_levels("game", 10, 12, 14, appid="1091500")
    assert s.effective("1091500")["pl3"] == 14
    assert s.effective(None)["pl1"] == 18  # global unchanged


def test_persists_and_lists(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    s1 = ProfileStore(path, default_watts=15)
    s1.set_levels("global", 20, 30, 35)
    s1.set_pl1("game", 8, appid="42")
    s2 = ProfileStore(path, default_watts=15)
    assert s2.effective(None)["pl1"] == 20 and s2.effective(None)["pl3"] == 35
    assert s2.effective(None)["auto"] is False
    assert s2.effective("42")["pl1"] == 8 and s2.effective("42")["auto"] is True
    assert s2.list_games() == ["42"]


def test_migrates_old_watts_shape_to_auto(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"watts": 22}, "games": {"7": {"watts": 9}}}, f)
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["pl1"] == 22 and s.effective(None)["auto"] is True
    assert s.effective(None)["pl2"] == 26  # round(22*1.2)
    assert s.effective("7")["pl1"] == 9


def test_migrates_old_absolute_flat_to_auto_distinct_to_manual(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 15, "pl2": 15, "pl3": 15},
                   "games": {"7": {"pl1": 15, "pl2": 25, "pl3": 30}}}, f)
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["auto"] is True  # flat old absolute -> auto
    g = s.effective("7")
    assert g["auto"] is False and (g["pl1"], g["pl2"], g["pl3"]) == (15, 25, 30)
