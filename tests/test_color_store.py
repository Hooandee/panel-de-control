import json

from display.color_store import ColorStore

# Native/neutral: saturation 100 (%, per-game); every other field is global panel
# calibration at its neutral (bipolar 0, or gain 100 = 1.0).
NATIVE = {
    "saturation": 100, "temperature": 0, "contrast": 0, "gamma": 0, "hue": 0, "black": 0,
    "gain_r": 100, "gain_g": 100, "gain_b": 100, "vibrance": 0,
}


def _store(tmp_path):
    return ColorStore(str(tmp_path / "color.json"))


def test_color_follow_global_keeps_own_saturation(tmp_path):
    s = _store(tmp_path)
    s.set_saturation("global", 120)
    s.set_saturation("game", 160, appid="42")
    assert s.effective("42")["saturation"] == 160
    s.set_follow_global("42", True)
    assert s.effective("42")["saturation"] == 120        # global applied
    assert s.has_game("42") and s.is_following_global("42") is True
    s.set_follow_global("42", False)
    assert s.effective("42")["saturation"] == 160        # own restored
    assert s.is_following_global("42") is False


def test_color_follow_global_persists(tmp_path):
    path = str(tmp_path / "c.json")
    s1 = ColorStore(path)
    s1.set_saturation("game", 140, appid="42")
    assert s1.is_following_global("42") is False
    s1.set_follow_global("42", True)
    s2 = ColorStore(path)
    assert s2.is_following_global("42") is True


def test_default_is_native(tmp_path):
    assert _store(tmp_path).effective(None) == NATIVE


def test_set_saturation_global(tmp_path):
    s = _store(tmp_path)
    s.set_saturation("global", 140)
    assert s.effective(None)["saturation"] == 140


def test_saturation_is_per_game_over_global(tmp_path):
    s = _store(tmp_path)
    s.set_saturation("global", 120)
    assert s.effective("123")["saturation"] == 120  # inherits global
    s.set_saturation("game", 160, appid="123")
    assert s.effective("123")["saturation"] == 160  # own override
    assert s.effective(None)["saturation"] == 120    # global untouched
    assert s.has_game("123") is True


def test_calibration_is_global_only(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", temperature=-40, contrast=25)
    s.set_saturation("game", 160, appid="123")
    eff = s.effective("123")
    assert eff["temperature"] == -40 and eff["contrast"] == 25
    assert eff["saturation"] == 160  # game override still applies


def test_set_calibration_clamps_bipolar(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", temperature=500, contrast=-999)
    eff = s.effective(None)
    assert eff["temperature"] == 100    # -100..100
    assert eff["contrast"] == -60       # floored so the panel never goes illegible


def test_advanced_calibration_fields_are_global(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", gamma=40, hue=-20, gain_r=120, gain_g=90, gain_b=110, vibrance=60)
    s.set_saturation("game", 160, appid="123")
    eff = s.effective("123")
    assert eff["gamma"] == 40 and eff["hue"] == -20 and eff["vibrance"] == 60
    assert eff["gain_r"] == 120 and eff["gain_g"] == 90 and eff["gain_b"] == 110
    assert eff["saturation"] == 160  # game override untouched


def test_advanced_calibration_clamps(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", gamma=999, hue=-999, gain_r=999, gain_b=-5, vibrance=999)
    eff = s.effective(None)
    assert eff["gamma"] == 100 and eff["hue"] == -100 and eff["vibrance"] == 100
    assert eff["gain_r"] == 150   # 50..150
    assert eff["gain_b"] == 50    # floored so a channel is never crushed to black


def test_every_native_field_has_a_range():
    # Guards the invariant _clean_global relies on: a NATIVE field without a range
    # would KeyError out of __init__ and hang the panel.
    from display import color_store
    from display.const import NATIVE as N
    assert set(N) <= set(color_store._RANGES)


def test_default_advanced_fields_are_neutral(tmp_path):
    eff = _store(tmp_path).effective(None)
    assert eff["gamma"] == 0 and eff["hue"] == 0 and eff["vibrance"] == 0 and eff["black"] == 0
    assert eff["gain_r"] == 100 and eff["gain_g"] == 100 and eff["gain_b"] == 100


def test_reset_clears_advanced_fields(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", gamma=50, gain_r=130, vibrance=40)
    s.reset()
    eff = s.effective(None)
    assert eff["gamma"] == 0 and eff["gain_r"] == 100 and eff["vibrance"] == 0


def test_set_saturation_clamps(tmp_path):
    s = _store(tmp_path)
    s.set_saturation("global", 999)
    assert s.effective(None)["saturation"] == 200  # 0..200
    s.set_saturation("global", -5)
    assert s.effective(None)["saturation"] == 0


def test_apply_preset_sets_calibration_and_global_saturation(tmp_path):
    s = _store(tmp_path)
    s.apply_preset("global", {"saturation": 140, "temperature": -10, "contrast": 30})
    eff = s.effective(None)
    assert eff["saturation"] == 140 and eff["contrast"] == 30 and eff["temperature"] == -10


def test_reset_returns_to_native_and_clears_games(tmp_path):
    s = _store(tmp_path)
    s.set_calibration("global", temperature=40, contrast=20)
    s.set_saturation("game", 170, appid="123")
    s.reset()
    assert s.effective(None) == NATIVE
    assert s.effective("123") == NATIVE
    assert s.has_game("123") is False


def test_robust_load_bad_json(tmp_path):
    p = tmp_path / "color.json"
    p.write_text("{ not json")
    assert ColorStore(str(p)).effective(None) == NATIVE


def test_partial_saved_data_fills_native_defaults(tmp_path):
    p = tmp_path / "color.json"
    p.write_text(json.dumps({"global": {"saturation": 150}}))
    eff = ColorStore(str(p)).effective(None)
    assert eff["saturation"] == 150
    assert eff["contrast"] == 0 and eff["temperature"] == 0  # missing → native


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "color.json")
    ColorStore(path).set_saturation("global", 133)
    assert ColorStore(path).effective(None)["saturation"] == 133


def test_apply_preset_keeps_hdr_global(tmp_path):
    s = _store(tmp_path)
    s.set_hdr("global", True)
    s.apply_preset("global", {"saturation": 140, "contrast": 20})  # a preset carries no hdr
    assert s.hdr(None) is True  # HDR is a display mode, not part of a look


def test_apply_preset_keeps_hdr_game(tmp_path):
    s = _store(tmp_path)
    s.set_hdr("game", True, appid="7")
    s.apply_preset("game", {"saturation": 130}, appid="7")
    assert s.hdr("7") is True


def test_reset_keeps_hdr(tmp_path):
    s = _store(tmp_path)
    s.set_hdr("global", True)
    s.set_saturation("global", 150)
    s.reset()
    assert s.effective(None)["saturation"] == 100  # color back to native
    assert s.hdr(None) is True                      # HDR mode survives a color reset


def test_migrates_old_saturation_only_game_entry_keeping_global_calibration(tmp_path):
    # Old shape: calibration was global, a game held ONLY its own saturation.
    path = str(tmp_path / "color.json")
    with open(path, "w") as f:
        json.dump({"global": {"contrast": 30, "temperature": -20},
                   "games": {"42": {"saturation": 160}}}, f)
    s = ColorStore(path)
    eff = s.effective("42")
    assert eff["saturation"] == 160     # its own saturation kept
    assert eff["contrast"] == 30        # global calibration inherited, not reset to native
    assert eff["temperature"] == -20
