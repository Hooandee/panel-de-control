import random
from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import pet
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))


def _at(hour, minute=0):
    return datetime(2026, 10, 22, hour, minute, tzinfo=TZ).timestamp()


def _ctx(now, game=None, metrics=None):
    return SceneContext(now=now, tz=TZ, game=game, metrics=metrics or {})


GAME = {"appid": "1", "name": "Hades", "started_at": _at(20) - 600}


def test_states_follow_what_is_happening():
    scene = pet.PetScene()
    assert scene.state(_ctx(_at(3))) == "sleep"
    assert scene.state(_ctx(_at(12))) == "idle"
    assert scene.state(_ctx(_at(20), GAME, {"gpu_temp": 60})) == "play"
    assert scene.state(_ctx(_at(20), GAME, {"gpu_temp": 85})) == "hot"
    assert scene.state(_ctx(_at(20), GAME, {"gpu_temp": 78})) == "hot"
    assert scene.state(_ctx(_at(20), GAME, {"gpu_temp": 72})) == "play"


def test_a_new_game_starts_with_a_short_party():
    scene = pet.PetScene()
    fresh = {"appid": "2", "name": "X", "started_at": _at(20)}
    assert scene.state(_ctx(_at(20) + 10, fresh)) == "party"
    assert scene.state(_ctx(_at(20) + 120, fresh)) == "play"


@pytest.mark.parametrize("state", pet.STATES)
def test_every_state_is_a_seamless_loop_within_size(state):
    segment = pet.PetScene().render_state(state, {})
    assert len(segment.frames) >= 8
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_an_evening_of_play_changes_scene_only_a_few_times_per_hour():
    scene, rng, changes, previous = pet.PetScene(), random.Random(2), 0, None
    for second in range(0, 3600, 2):
        temp = 76 + rng.uniform(-6, 6)
        key = scene.key(_ctx(_at(20) + second, GAME, {"gpu_temp": temp}))
        if key != previous:
            changes, previous = changes + 1, key
    assert changes <= pet.PetScene.UPLOADS_PER_HOUR


def test_pet_changes_pastime_by_the_hour_at_most():
    keys = {pet.PetScene().key(_ctx(_at(12, m))) for m in range(60)}
    assert len(keys) == 1
    activities = {pet.activity_for(_at(h)) for h in range(24)}
    assert len(activities) >= 3


@pytest.mark.parametrize("activity", pet.ACTIVITIES)
def test_every_pastime_moves_and_fits(activity):
    segment = pet.PetScene().render_state("idle", {}, activity)
    assert len({tuple(frame.pixels()) for frame in segment.frames}) >= 10
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES
