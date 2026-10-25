import base64
from datetime import timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec, demo, library
from accessories.jsaux_pixel.scenes import catalog
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))
NOW = 1_800_000_000.0
ART = {
    "appid": "3768760", "name": "007 First Light",
    "rgb": base64.b64encode(bytes([200, 120, 40]) * (64 * 54)).decode(),
    "portrait": base64.b64encode(bytes([30, 60, 200]) * (36 * 54)).decode(),
    "playtime_min": 7579, "achievements": {"done": 23, "total": 50},
}


@pytest.fixture
def scenes(tmp_path):
    return {scene.id: scene for _, scene in catalog.build(library.Library(tmp_path))}


def test_the_reel_shows_every_wow_scene_and_each_fits_one_upload(scenes):
    reel = demo.reel(ART)
    assert [item.id for item in reel][:2] == ["hooandee", "pet_happy"]
    assert {"pet_sad", "weather_sun", "weather_storm", "cover_full", "cover_side", "speedrun", "layout"} <= {i.id for i in reel}
    for item in reel:
        segment = item.render(scenes, NOW, TZ)
        assert segment.frames, item.id
        assert encoded_size(segment) <= codec.MAX_GIF_BYTES, item.id


def test_without_game_art_the_cover_shots_are_left_out():
    ids = {item.id for item in demo.reel(None)}
    assert "cover_full" not in ids and "cover_side" not in ids


def test_the_weather_is_in_seville():
    assert demo.SEVILLE["name"] == "Sevilla"


def test_cover_shots_use_the_art_sent_by_the_ui(scenes):
    item = next(i for i in demo.reel(ART) if i.id == "cover_full")
    assert item.render(scenes, NOW, TZ).frames[0].get(10, 10) == (200, 120, 40)
