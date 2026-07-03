import json

from display.color_store import ColorStore

# Native/neutral: saturation 100 (%), neutral temperature & contrast (both bipolar,
# 0 = neutral). saturation is the per-game field; temperature/contrast are global.
NATIVE = {"saturation": 100, "temperature": 0, "contrast": 0}


def _store(tmp_path):
    return ColorStore(str(tmp_path / "color.json"))


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
    s.set_calibration(temperature=-40, contrast=25)
    s.set_saturation("game", 160, appid="123")
    eff = s.effective("123")
    assert eff["temperature"] == -40 and eff["contrast"] == 25
    assert eff["saturation"] == 160  # game override still applies


def test_set_calibration_clamps_bipolar(tmp_path):
    s = _store(tmp_path)
    s.set_calibration(temperature=500, contrast=-999)
    eff = s.effective(None)
    assert eff["temperature"] == 100    # -100..100
    assert eff["contrast"] == -60       # floored so the panel never goes illegible


def test_set_saturation_clamps(tmp_path):
    s = _store(tmp_path)
    s.set_saturation("global", 999)
    assert s.effective(None)["saturation"] == 200  # 0..200
    s.set_saturation("global", -5)
    assert s.effective(None)["saturation"] == 0


def test_apply_preset_sets_calibration_and_global_saturation(tmp_path):
    s = _store(tmp_path)
    s.apply_preset({"saturation": 140, "temperature": -10, "contrast": 30})
    eff = s.effective(None)
    assert eff["saturation"] == 140 and eff["contrast"] == 30 and eff["temperature"] == -10


def test_reset_returns_to_native_and_clears_games(tmp_path):
    s = _store(tmp_path)
    s.set_calibration(temperature=40, contrast=20)
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
