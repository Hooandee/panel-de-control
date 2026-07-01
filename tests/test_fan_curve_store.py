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


# ---------------------------------------------------------------------------
# Adaptive mode — a first-class, selectable curve mode. It carries NO stored
# points (like auto): the learned curve is computed live from telemetry when
# driven, so there's never a stale curve to serve. A per-scope silence↔cool
# `bias` preference is the only persisted state.
# ---------------------------------------------------------------------------

def test_adaptive_is_valid_preset_with_no_points(tmp_path):
    s = _store(tmp_path)
    s.set_adaptive("game", appid="123")
    eff = s.effective("123")
    assert eff["preset"] == "adaptive"
    assert eff["points"] is None
    assert eff["bias"] == 0  # neutral by default


def test_adaptive_inherits_global(tmp_path):
    s = _store(tmp_path)
    s.set_adaptive("global")
    assert s.effective("999")["preset"] == "adaptive"  # game with no profile


def test_set_adaptive_bias_persists_and_clamps(tmp_path):
    s = _store(tmp_path)
    s.set_adaptive("game", appid="123")
    s.set_adaptive_bias("game", 200, appid="123")   # over-range → clamps to +100
    assert s.effective("123")["bias"] == 100
    s.set_adaptive_bias("game", -400, appid="123")
    assert s.effective("123")["bias"] == -100
    s.set_adaptive_bias("game", -30, appid="123")
    assert s.effective("123")["bias"] == -30
    # Setting the bias keeps the mode adaptive with no points.
    assert s.effective("123")["preset"] == "adaptive" and s.effective("123")["points"] is None


def test_set_adaptive_bias_switches_to_adaptive(tmp_path):
    # Moving the dial from a non-adaptive scope selects adaptive (the dial only
    # shows inside the adaptive card, but be robust).
    s = _store(tmp_path)
    s.set_custom("game", PTS, appid="123")
    s.set_adaptive_bias("game", 40, appid="123")
    assert s.effective("123")["preset"] == "adaptive"
    assert s.effective("123")["bias"] == 40


def test_adaptive_persists_across_instances(tmp_path):
    path = str(tmp_path / "fan_curves.json")
    st = FanCurveStore(path)
    st.set_adaptive("game", appid="123")
    st.set_adaptive_bias("game", -50, appid="123")
    eff = FanCurveStore(path).effective("123")
    assert eff["preset"] == "adaptive" and eff["bias"] == -50


def test_switching_away_from_adaptive_clears_it(tmp_path):
    s = _store(tmp_path)
    s.set_adaptive("game", appid="123")
    s.set_preset("game", "silent", PTS, appid="123")
    assert s.effective("123")["preset"] == "silent"


# ---------------------------------------------------------------------------
# Migration of REAL old data: a legacy profile written by the old auto-apply
# carried preset=="custom" + learned:true. It must load as `adaptive` (the mode
# that now represents a learned curve), never crash, and lose the dead flag.
# ---------------------------------------------------------------------------

def _write_raw(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def test_migration_legacy_learned_custom_becomes_adaptive(tmp_path):
    path = str(tmp_path / "fan_curves.json")
    _write_raw(path, {"global": {"preset": "auto", "points": None},
                      "games": {"123": {"preset": "custom", "points": PTS, "learned": True}}})
    eff = FanCurveStore(path).effective("123")
    assert eff["preset"] == "adaptive"
    assert eff["points"] is None
    assert eff["bias"] == 0


def test_migration_hand_set_custom_stays_custom(tmp_path):
    path = str(tmp_path / "fan_curves.json")
    _write_raw(path, {"games": {"123": {"preset": "custom", "points": PTS}}})
    eff = FanCurveStore(path).effective("123")
    assert eff["preset"] == "custom"
    assert eff["points"] == PTS


def test_migration_learned_false_stays_custom(tmp_path):
    path = str(tmp_path / "fan_curves.json")
    _write_raw(path, {"games": {"123": {"preset": "custom", "points": PTS, "learned": False}}})
    assert FanCurveStore(path).effective("123")["preset"] == "custom"


def test_adaptive_with_stray_points_loads_without_them(tmp_path):
    # Robustness: an adaptive profile that somehow has points → still no points.
    path = str(tmp_path / "fan_curves.json")
    _write_raw(path, {"global": {"preset": "adaptive", "points": PTS, "bias": 20}})
    eff = FanCurveStore(path).effective(None)
    assert eff["preset"] == "adaptive"
    assert eff["points"] is None
    assert eff["bias"] == 20
