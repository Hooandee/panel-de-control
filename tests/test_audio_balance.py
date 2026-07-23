from audio.const import balance_channels, clamp_balance
from audio.eq_store import EqStore


def test_clamp_balance_range_and_type():
    assert clamp_balance(0) == 0
    assert clamp_balance(200) == 100
    assert clamp_balance(-200) == -100
    assert clamp_balance(33.9) == 33
    assert clamp_balance("x") == 0
    assert clamp_balance(None) == 0
    assert clamp_balance(float("inf")) == 100
    assert clamp_balance(float("-inf")) == -100
    assert clamp_balance(float("nan")) == 0
    assert clamp_balance(10**4000) == 0
    assert clamp_balance(-(10**4000)) == 0


def test_balance_channels_center_is_unity():
    assert balance_channels(0) == (100, 100)


def test_balance_channels_full_right_mutes_left():
    assert balance_channels(100) == (0, 100)


def test_balance_channels_full_left_mutes_right():
    assert balance_channels(-100) == (100, 0)


def test_balance_channels_attenuates_far_side_only():
    assert balance_channels(40) == (60, 100)
    assert balance_channels(-25) == (100, 75)


def test_balance_channels_clamps_out_of_range():
    assert balance_channels(500) == (0, 100)


def test_balance_defaults_center_and_sets(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    assert s.effective(appid=None, route="speaker")["balance"] == 0
    s.set_balance("global", "speaker", -30)
    assert s.effective(appid=None, route="speaker")["balance"] == -30


def test_balance_clamped(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_balance("global", "speaker", 999)
    assert s.effective(appid=None, route="speaker")["balance"] == 100


def test_balance_per_route_independent(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_balance("global", "speaker", 20)
    assert s.effective(appid=None, route="headphone")["balance"] == 0


def test_balance_preserved_when_curve_bass_loudness_change(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_balance("global", "speaker", -40)
    s.set_band("global", "speaker", 0, 4.0)
    s.set_bass("global", "speaker", 50)
    s.set_loudness("global", "speaker", True)
    assert s.effective(appid=None, route="speaker")["balance"] == -40


def test_curve_preserved_when_balance_changes(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_band("global", "speaker", 0, 6.0)
    s.set_bass("global", "speaker", 30)
    s.set_balance("global", "speaker", 15)
    eff = s.effective(appid=None, route="speaker")
    assert eff["gains"][0] == 6.0 and eff["bass"] == 30 and eff["preset"] == "custom"


def test_balance_per_game_inherits_global(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_balance("global", "speaker", 25)
    assert s.effective(appid="123", route="speaker")["balance"] == 25


def test_reset_clears_balance(tmp_path):
    s = EqStore(str(tmp_path / "audio.json"))
    s.set_balance("global", "speaker", 60)
    s.reset("global", "speaker")
    assert s.effective(appid=None, route="speaker")["balance"] == 0
