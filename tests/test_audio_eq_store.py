import json

from audio.eq_store import EqStore


def test_malformed_games_shape_does_not_crash(tmp_path):
    p = tmp_path / "audio.json"
    p.write_text(json.dumps({"global": {}, "games": [{}]}))
    s = EqStore(str(p))
    assert s.list_games() == []
    assert s.effective(appid=None, route="speaker")["gains"] == [0.0] * 10


def test_global_defaults_flat(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    eff = s.effective(appid=None, route="speaker")
    assert eff["gains"] == [0.0] * 10
    assert eff["preset"] == "flat"


def test_per_game_inherits_global(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 0, 3.0)
    eff = s.effective(appid="12345", route="speaker")  # game with no own profile
    assert eff["gains"][0] == 3.0


def test_route_independent(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 5, 5.0)
    assert s.effective(appid=None, route="headphone")["gains"][5] == 0.0


def test_set_band_marks_custom_and_recomputes_preamp(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 1, 8.0)
    eff = s.effective(appid=None, route="speaker")
    assert eff["gains"][1] == 8.0
    assert eff["preset"] == "custom"
    assert eff["preamp"] == -8.0


def test_set_setting_replaces_route(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_setting("global", "speaker", {"preset": "bass", "gains": [4.0] * 10, "preamp": -4.0})
    eff = s.effective(appid=None, route="speaker")
    assert eff["preset"] == "bass" and eff["gains"] == [4.0] * 10


def test_set_bands_clamps_pads_and_marks_custom(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_bands("global", "speaker", [99, -99, 3])  # over-range + short list
    eff = s.effective(appid=None, route="speaker")
    assert eff["gains"] == [12.0, -12.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert eff["preset"] == "custom"
    assert eff["preamp"] == -12.0


def test_bass_defaults_zero_and_sets(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    assert s.effective(appid=None, route="speaker")["bass"] == 0
    s.set_bass("global", "speaker", 70)
    assert s.effective(appid=None, route="speaker")["bass"] == 70


def test_bass_preserved_when_curve_changes(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_bass("global", "speaker", 50)
    s.set_band("global", "speaker", 0, 4.0)
    s.set_setting("global", "speaker", {"preset": "bass", "gains": [2.0] * 10})
    assert s.effective(appid=None, route="speaker")["bass"] == 50  # survived both


def test_bass_clamped(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_bass("global", "speaker", 999)
    assert s.effective(appid=None, route="speaker")["bass"] == 100


def test_loudness_toggle_and_preserved(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    assert s.effective(appid=None, route="speaker")["loudness"] is False
    s.set_loudness("global", "speaker", True)
    s.set_band("global", "speaker", 0, 4.0)  # curve edit keeps loudness
    s.set_bass("global", "speaker", 50)       # bass change keeps loudness
    assert s.effective(appid=None, route="speaker")["loudness"] is True


def test_reset_clears_bass(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_bass("global", "speaker", 80)
    s.reset("global", "speaker")
    assert s.effective(appid=None, route="speaker")["bass"] == 0


def test_reset_route_to_flat(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 0, 9.0)
    s.reset("global", "speaker")
    assert s.effective(appid=None, route="speaker")["gains"] == [0.0] * 10


def test_game_can_follow_global(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 0, 2.0)
    s.set_band("game", "speaker", 0, 7.0, appid="42")  # game gets its own
    assert s.effective(appid="42", route="speaker")["gains"][0] == 7.0
    s.set_follow_global("42", True)
    assert s.effective(appid="42", route="speaker")["gains"][0] == 2.0  # follows global again


def test_load_robust_on_garbage(tmp_path):
    p = tmp_path / "audio.json"
    p.write_text("{ not json")
    s = EqStore(str(p))
    assert s.effective(appid=None, route="speaker")["gains"] == [0.0] * 10


# --- spatial effects: crossfeed (headphone) + stereo width (speaker) ------------------

def test_spatial_defaults(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    eff = s.effective(appid=None, route="headphone")
    assert eff["crossfeed"] == 0          # off by default
    assert eff["stereo_width"] == 50      # neutral by default (NOT 0 = mono)


def test_crossfeed_set_and_clamped(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_crossfeed("global", "headphone", 60)
    assert s.effective(appid=None, route="headphone")["crossfeed"] == 60
    s.set_crossfeed("global", "headphone", 999)
    assert s.effective(appid=None, route="headphone")["crossfeed"] == 100


def test_stereo_width_set_and_clamped(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_stereo_width("global", "speaker", 80)
    assert s.effective(appid=None, route="speaker")["stereo_width"] == 80
    s.set_stereo_width("global", "speaker", -5)
    assert s.effective(appid=None, route="speaker")["stereo_width"] == 0


def test_spatial_preserved_across_curve_bass_loudness(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_crossfeed("global", "headphone", 40)
    s.set_band("global", "headphone", 0, 4.0)
    s.set_bass("global", "headphone", 30)
    s.set_loudness("global", "headphone", True)
    s.set_setting("global", "headphone", {"preset": "music", "gains": [1.0] * 10})
    assert s.effective(appid=None, route="headphone")["crossfeed"] == 40  # survived all


def test_curve_edit_preserves_width(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_stereo_width("global", "speaker", 75)
    s.set_bands("global", "speaker", [2.0] * 10)
    assert s.effective(appid=None, route="speaker")["stereo_width"] == 75


def test_reset_returns_spatial_to_neutral(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_crossfeed("global", "headphone", 90)
    s.reset("global", "headphone")
    eff = s.effective(appid=None, route="headphone")
    assert eff["crossfeed"] == 0 and eff["stereo_width"] == 50


def test_legacy_setting_without_spatial_fields_migrates(tmp_path):
    p = tmp_path / "audio.json"
    p.write_text(json.dumps({"global": {"speaker": {"gains": [1.0] * 10, "bass": 20}}}))
    s = EqStore(str(p))
    eff = s.effective(appid=None, route="speaker")
    assert eff["bass"] == 20 and eff["crossfeed"] == 0 and eff["stereo_width"] == 50
