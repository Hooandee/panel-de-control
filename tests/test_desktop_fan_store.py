from desktop.fan_store import DesktopFanStore


POINTS = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]


def test_defaults_both_channels_to_firmware_auto(tmp_path):
    store = DesktopFanStore(str(tmp_path / "fans.json"))
    assert store.effective(None) == {
        "system": {"preset": "auto", "points": None},
        "gpu": {"preset": "auto", "points": None},
    }


def test_channels_are_persisted_independently(tmp_path):
    path = str(tmp_path / "fans.json")
    store = DesktopFanStore(path)
    store.set_channel("global", "system", "silent", POINTS)
    reloaded = DesktopFanStore(path).effective(None)
    assert reloaded["system"]["preset"] == "silent"
    assert reloaded["gpu"]["preset"] == "auto"


def test_game_can_override_only_one_channel_without_losing_the_other(tmp_path):
    store = DesktopFanStore(str(tmp_path / "fans.json"))
    store.set_channel("global", "gpu", "performance", POINTS)
    store.set_channel("game", "system", "silent", POINTS, "42")
    effective = store.effective("42")
    assert effective["system"]["preset"] == "silent"
    assert effective["gpu"]["preset"] == "performance"
