import json

from fan_curves import FanCurveStore

PTS = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]


def _store(tmp_path):
    return FanCurveStore(str(tmp_path / "fan_curves.json"))


def test_default_is_auto(tmp_path):
    eff = _store(tmp_path).effective(None)
    assert eff["preset"] == "auto"
    assert eff["points"] is None


def test_set_preset_persists_points(tmp_path):
    s = _store(tmp_path)
    s.set_preset("global", "balanced", PTS)
    eff = s.effective(None)
    assert eff["preset"] == "balanced"
    assert eff["points"] == PTS


def test_set_custom_marks_custom(tmp_path):
    s = _store(tmp_path)
    s.set_custom("global", PTS)
    assert s.effective(None)["preset"] == "custom"


def test_set_auto_clears_points(tmp_path):
    s = _store(tmp_path)
    s.set_custom("global", PTS)
    s.set_auto("global")
    eff = s.effective(None)
    assert eff["preset"] == "auto" and eff["points"] is None


def test_game_inherits_then_overrides(tmp_path):
    s = _store(tmp_path)
    s.set_preset("global", "silent", PTS)
    assert s.effective("123")["preset"] == "silent"  # inherits global
    s.set_preset("game", "performance", PTS, appid="123")
    assert s.effective("123")["preset"] == "performance"
    assert s.effective(None)["preset"] == "silent"  # global untouched
    assert s.has_game("123") is True


def test_create_game_from_global(tmp_path):
    s = _store(tmp_path)
    s.set_preset("global", "balanced", PTS)
    s.create_game_from_global("123")
    assert s.effective("123")["preset"] == "balanced"


def test_robust_load_bad_json(tmp_path):
    p = tmp_path / "fan_curves.json"
    p.write_text("{ not json")
    eff = FanCurveStore(str(p)).effective(None)
    assert eff["preset"] == "auto"


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "fan_curves.json")
    FanCurveStore(path).set_preset("global", "silent", PTS)
    assert FanCurveStore(path).effective(None)["preset"] == "silent"
    assert "global" in json.loads(open(path).read())
