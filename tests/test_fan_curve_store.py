import json
from pathlib import Path

import pytest

from fan_curves import FanCurveStore

PTS = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]


def _store(tmp_path):
    return FanCurveStore(str(tmp_path / "fan_curves.json"))


def test_default_is_auto(tmp_path):
    eff = _store(tmp_path).effective(None)
    assert eff["preset"] == "auto"
    assert eff["points"] is None


def test_fan_follow_global_applies_global_keeps_own(tmp_path):
    s = _store(tmp_path)
    s.set_preset("global", "balanced", PTS)
    s.set_preset("game", "performance", PTS, appid="42")
    assert s.effective("42")["preset"] == "performance"
    s.set_follow_global("42", True)
    assert s.effective("42")["preset"] == "balanced"     # global applied
    assert s.has_game("42") and s.is_following_global("42") is True
    s.set_follow_global("42", False)
    assert s.effective("42")["preset"] == "performance"  # own restored, never lost


def test_fan_game_without_profile_follows_global(tmp_path):
    assert _store(tmp_path).is_following_global("999") is True


def test_fan_follow_global_persists(tmp_path):
    path = str(tmp_path / "f.json")
    s1 = FanCurveStore(path)
    s1.set_preset("game", "silent", PTS, appid="42")
    assert s1.is_following_global("42") is False
    s1.set_follow_global("42", True)
    s2 = FanCurveStore(path)
    assert s2.is_following_global("42") is True


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


@pytest.fixture
def custom_restore():
    return json.loads((Path(__file__).parent / "data" / "fan_custom_restore.json").read_text())


@pytest.mark.parametrize("mode", ["performance", "auto", "adaptive"])
def test_manual_curve_survives_mode_switch_and_reload(tmp_path, custom_restore, mode):
    path = str(tmp_path / "fan_curves.json")
    store = FanCurveStore(path)
    store.set_custom("global", custom_restore["custom_points"])
    if mode == "performance":
        store.set_preset("global", custom_restore["preset"], custom_restore["preset_points"])
    elif mode == "auto":
        store.set_auto("global")
    else:
        store.set_adaptive("global")
    profile = FanCurveStore(path).effective(None)
    assert profile["preset"] == mode
    assert profile["points"] == (custom_restore["preset_points"] if mode == "performance" else None)
    assert profile["custom_points"] == custom_restore["custom_points"]
    restored = FanCurveStore(path)
    restored.set_custom("global", profile["custom_points"])
    assert FanCurveStore(path).effective(None) == {"preset": "custom", "points": custom_restore["custom_points"]}


def test_adaptive_bias_keeps_manual_curve_while_bias_changes(tmp_path, custom_restore):
    path = str(tmp_path / "fan_curves.json")
    store = FanCurveStore(path)
    store.set_custom("global", custom_restore["custom_points"])
    store.set_adaptive_bias("global", 25)
    store.set_adaptive_bias("global", -30)
    profile = FanCurveStore(path).effective(None)
    assert profile == {"preset": "adaptive", "points": None, "bias": -30, "custom_points": custom_restore["custom_points"]}


def test_game_mode_keeps_own_manual_curve_instead_of_followed_global(tmp_path, custom_restore):
    path = str(tmp_path / "fan_curves.json")
    store = FanCurveStore(path)
    store.set_custom("global", custom_restore["custom_points"])
    store.set_custom("game", custom_restore["preset_points"], appid="game-a")
    store.set_follow_global("game-a", True)
    store.set_auto("game", appid="game-a")
    assert store.is_following_global("game-a") is False
    store.set_preset("global", custom_restore["preset"], custom_restore["preset_points"])
    loaded = FanCurveStore(path)
    assert loaded.effective(None)["custom_points"] == custom_restore["custom_points"]
    assert loaded.game_profile("game-a")["custom_points"] == custom_restore["preset_points"]
    loaded.set_custom("game", loaded.game_profile("game-a")["custom_points"], appid="game-a")
    assert FanCurveStore(path).effective("game-a")["points"] == custom_restore["preset_points"]
    assert FanCurveStore(path).effective(None)["custom_points"] == custom_restore["custom_points"]


def test_first_game_mode_preserves_inherited_manual_curve_without_changing_global(tmp_path, custom_restore):
    store = _store(tmp_path)
    store.set_custom("global", custom_restore["custom_points"])
    store.set_auto("game", appid="game-a")
    assert store.effective("game-a")["custom_points"] == custom_restore["custom_points"]
    assert store.effective(None) == {"preset": "custom", "points": custom_restore["custom_points"]}


def test_new_manual_curve_replaces_saved_curve_and_has_no_stale_cache(tmp_path, custom_restore):
    store = _store(tmp_path)
    store.set_custom("global", custom_restore["custom_points"])
    store.set_auto("global")
    store.set_custom("global", custom_restore["preset_points"])
    assert store.effective(None) == {"preset": "custom", "points": custom_restore["preset_points"]}
    store.set_auto("global")
    assert store.effective(None)["custom_points"] == custom_restore["preset_points"]


def test_loading_custom_uses_active_points_and_discards_obsolete_cache(tmp_path, custom_restore):
    path = tmp_path / "fan_curves.json"
    _write_raw(path, {"global": {"preset": "custom", "points": custom_restore["custom_points"], "custom_points": custom_restore["preset_points"]}})
    assert FanCurveStore(str(path)).effective(None) == {"preset": "custom", "points": custom_restore["custom_points"]}


def test_learned_custom_migration_never_creates_a_manual_curve(tmp_path, custom_restore):
    path = tmp_path / "fan_curves.json"
    _write_raw(path, {"global": {"preset": "custom", "points": custom_restore["custom_points"], "learned": True, "custom_points": custom_restore["preset_points"]}})
    store = FanCurveStore(str(path))
    assert store.effective(None) == {"preset": "adaptive", "points": None, "bias": 0}
    store.set_auto("global")
    assert "custom_points" not in FanCurveStore(str(path)).effective(None)


@pytest.mark.parametrize("cache", [[], [[40]], "invalid", [[40, None]]])
def test_loading_noncustom_ignores_invalid_manual_cache(tmp_path, custom_restore, cache):
    path = tmp_path / "fan_curves.json"
    _write_raw(path, {"global": {"preset": custom_restore["preset"], "points": custom_restore["preset_points"], "custom_points": cache}})
    assert FanCurveStore(str(path)).effective(None) == {"preset": custom_restore["preset"], "points": custom_restore["preset_points"]}
