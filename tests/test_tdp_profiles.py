import json

from tdp_profiles import ProfileStore


def _store(tmp_path, default=15):
    return ProfileStore(str(tmp_path / "tdp_profiles.json"), default_watts=default)


def test_global_default_is_estable_and_flat(tmp_path):
    s = _store(tmp_path, default=15)
    eff = s.effective(None)
    assert eff["pl1"] == 15
    assert eff["pl2"] == 15 and eff["pl3"] == 15  # flat: SPPT = FPPT = PL1
    assert eff["mode"] == "estable"
    assert eff["watts"] == 15  # back-compat alias = pl1
    assert s.effective("1091500")["pl1"] == 15  # no game profile -> global


def test_set_pl1_keeps_estable_flat(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 12)
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (12, 12, 12)
    assert eff["mode"] == "estable"


def test_auto_mode_derives_managed_headroom(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 12)
    s.set_boost_mode("global", "auto")
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (12, 14, 17)  # round(14.4)/round(16.8)
    assert eff["mode"] == "auto"


def test_set_offsets_goes_custom(tmp_path):
    s = _store(tmp_path)  # default pl1=15
    s.set_offsets("global", 8, 4)
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (15, 23, 27)
    assert eff["mode"] == "custom"


def test_set_levels_absolute_api_stores_custom(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 15, 25, 30)  # absolute API -> off2=10, off3=5
    eff = s.effective(None)
    assert (eff["pl1"], eff["pl2"], eff["pl3"]) == (15, 25, 30)
    assert eff["mode"] == "custom"


def test_set_pl1_preserves_custom_margins_no_bounce(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 17)
    s.set_offsets("global", 20, 10)
    assert s.effective(None)["pl2"] == 37 and s.effective(None)["pl3"] == 47
    s.set_pl1("global", 35)  # raise PL1: margins preserved (unclamped intent)
    assert s.effective(None)["pl2"] == 55 and s.effective(None)["pl3"] == 65
    s.set_pl1("global", 17)  # lower again: margins fully restored, no shrink
    assert s.effective(None)["pl2"] == 37 and s.effective(None)["pl3"] == 47


def test_set_pl1_preserves_custom_margins_in_game_scope(tmp_path):
    s = _store(tmp_path)
    s.set_offsets("game", 8, 4, appid="42")  # creates custom game profile
    s.set_pl1("game", 20, appid="42")
    eff = s.effective("42")
    assert eff["pl2"] == 28 and eff["pl3"] == 32 and eff["mode"] == "custom"


def test_set_boost_mode_switches_between_modes(tmp_path):
    s = _store(tmp_path)
    s.set_offsets("global", 8, 4)
    assert s.effective(None)["mode"] == "custom"
    s.set_boost_mode("global", "auto")
    assert s.effective(None)["mode"] == "auto" and s.effective(None)["pl2"] == 18
    s.set_boost_mode("global", "estable")
    eff = s.effective(None)
    assert eff["mode"] == "estable" and eff["pl2"] == 15 and eff["pl3"] == 15
    # switching back to custom keeps the stored margins
    s.set_boost_mode("global", "custom")
    assert s.effective(None)["pl2"] == 23 and s.effective(None)["pl3"] == 27


def test_set_boost_mode_unknown_falls_back_to_estable(tmp_path):
    s = _store(tmp_path)
    s.set_boost_mode("global", "turbo")  # not a real mode
    assert s.effective(None)["mode"] == "estable"


def test_auto_to_custom_seeds_offsets_from_derived_rails(tmp_path):
    s = _store(tmp_path)
    s.set_pl1("global", 20)
    s.set_boost_mode("global", "auto")  # rails 20/24/28
    s.set_boost_mode("global", "custom")  # seed offsets so it doesn't drop to flat
    eff = s.effective(None)
    assert eff["mode"] == "custom" and (eff["pl2"], eff["pl3"]) == (24, 28)


def test_estable_to_custom_stays_flat(tmp_path):
    s = _store(tmp_path)  # default estable, no margins
    s.set_boost_mode("global", "custom")
    eff = s.effective(None)
    assert eff["mode"] == "custom" and (eff["pl2"], eff["pl3"]) == (15, 15)


def test_custom_margins_survive_mode_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.set_offsets("global", 8, 4)  # custom 15/23/27
    s.set_boost_mode("global", "estable")
    s.set_boost_mode("global", "custom")  # must NOT be overwritten by seeding
    eff = s.effective(None)
    assert (eff["pl2"], eff["pl3"]) == (23, 27)


def test_clean_tolerates_null_offsets_with_mode(tmp_path):
    # A malformed/partial persisted profile must never crash the shape-validator.
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 15, "mode": "auto", "off2": None}}, f)
    s = ProfileStore(path, default_watts=15)
    eff = s.effective(None)
    assert eff["mode"] == "auto" and eff["pl1"] == 15  # loaded, no crash


def test_create_game_copies_global_then_overrides(tmp_path):
    s = _store(tmp_path)
    s.set_levels("global", 18, 20, 22)
    s.create_game_from_global("1091500")
    assert s.has_game("1091500")
    g = s.effective("1091500")
    assert g["pl1"] == 18 and g["pl2"] == 20 and g["mode"] == "custom"
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
    assert s2.effective(None)["mode"] == "custom"
    assert s2.effective("42")["pl1"] == 8 and s2.effective("42")["mode"] == "estable"
    assert s2.list_games() == ["42"]


# ---- migration ----------------------------------------------------------------

def test_migrates_old_auto_default_to_estable(tmp_path):
    """The old silent default (off2/off3=None -> derived 1.2x/1.4x boost) migrates to
    flat, so a stale install stops over-drawing at the same TDP number."""
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 15, "off2": None, "off3": None}}, f)
    s = ProfileStore(path, default_watts=15)
    eff = s.effective(None)
    assert eff["mode"] == "estable"
    assert eff["pl2"] == 15 and eff["pl3"] == 15


def test_migrates_old_custom_offsets_to_custom(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 17, "off2": 8, "off3": 4}}, f)
    s = ProfileStore(path, default_watts=15)
    eff = s.effective(None)
    assert eff["mode"] == "custom" and (eff["pl2"], eff["pl3"]) == (25, 29)


def test_migrates_mixed_offsets_to_estable(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 15, "off3": 5}}, f)  # off2 missing -> None
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["mode"] == "estable" and s.effective(None)["pl2"] == 15


def test_migrates_old_watts_shape_to_estable(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"watts": 22}, "games": {"7": {"watts": 9}}}, f)
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["pl1"] == 22 and s.effective(None)["mode"] == "estable"
    assert s.effective(None)["pl2"] == 22 and s.effective(None)["pl3"] == 22
    assert s.effective("7")["pl1"] == 9


def test_migrates_old_absolute_flat_to_estable_scaled_to_custom(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    with open(path, "w") as f:
        json.dump({"global": {"pl1": 15, "pl2": 15, "pl3": 15},
                   "games": {"7": {"pl1": 15, "pl2": 25, "pl3": 30}}}, f)
    s = ProfileStore(path, default_watts=15)
    assert s.effective(None)["mode"] == "estable"  # flat old absolute -> estable
    g = s.effective("7")
    assert g["mode"] == "custom" and (g["pl1"], g["pl2"], g["pl3"]) == (15, 25, 30)


def test_new_mode_shape_round_trips(tmp_path):
    path = str(tmp_path / "tdp_profiles.json")
    s1 = ProfileStore(path, default_watts=15)
    s1.set_boost_mode("global", "auto")
    s2 = ProfileStore(path, default_watts=15)
    assert s2.effective(None)["mode"] == "auto" and s2.effective(None)["pl2"] == 18
