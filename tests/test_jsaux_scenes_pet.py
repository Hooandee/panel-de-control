import random
from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import pet, pet_mind
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))


def _at(hour, minute=0, day=22):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ).timestamp()


BORN = _at(9)


def _scene(tmp_path=None, born=BORN, seed=1):
    mind = pet_mind.Mind(tmp_path / "pet.json" if tmp_path else None, clock=lambda: born, rng=random.Random(seed))
    return pet.PetScene(mind)


def _ctx(now, game=None, metrics=None, events=None, options=None):
    return SceneContext(now=now, tz=TZ, game=game, metrics=metrics or {}, events=events or {}, options=options or {})


def _game(now, appid="1", tags=(19,), started=None):
    started = now - 600 if started is None else started
    game = {"appid": appid, "name": "Juego", "started_at": started}
    return game, {"game_info": {"appid": appid, "tags": list(tags)}}


def test_situations_follow_what_is_happening():
    scene = _scene()
    assert scene.situation(_ctx(_at(12))) == "home"
    game, events = _game(_at(20), tags=(699,))
    assert scene.situation(_ctx(_at(20), game, {"gpu_temp": 60}, events)) == "game:racing"
    assert scene.situation(_ctx(_at(20), game, {"gpu_temp": 85}, events)) == "hot"
    assert scene.situation(_ctx(_at(20), game, {"gpu_temp": 78}, events)) == "hot"
    assert scene.situation(_ctx(_at(20), game, {"gpu_temp": 70}, events)) == "game:racing"
    assert scene.situation(_ctx(_at(20), game, {"fan_pct": 0.95}, events)) == "windy"
    assert scene.situation(_ctx(_at(20), game, {"fan_pct": 0.7}, events)) == "windy"
    assert scene.situation(_ctx(_at(20), game, {"fan_pct": 0.5}, events)) == "game:racing"


def test_it_sleeps_when_its_mind_is_asleep():
    scene = _scene()
    scene.mind.observe(_at(23), night=True, playing=False)
    assert scene.situation(_ctx(_at(23, 30))) == "night"


@pytest.mark.parametrize("tags,reaction", [((1667,), "scared"), ((19,), "party"), ((699,), "party")])
def test_a_new_game_gets_a_reaction_to_its_genre(tags, reaction):
    scene = _scene()
    now = _at(20)
    game, events = _game(now, tags=tags, started=now - 5)
    ctx = _ctx(now, game, events=events)
    scene.key(ctx)
    assert scene.script(ctx)[0][0] == reaction


def test_the_favourite_genre_gets_excitement():
    scene = _scene()
    for i in range(3):
        scene.mind.saw_game(str(i), "racing", _at(10) + i)
    now = _at(20)
    game, events = _game(now, appid="9", tags=(699,), started=now - 5)
    ctx = _ctx(now, game, events=events)
    scene.key(ctx)
    assert scene.script(ctx)[0][0] == "excited"


def test_practice_turns_fright_into_a_flinch():
    scene = _scene()
    for i in range(8):
        scene.mind.saw_game(str(i), "horror", _at(10) + i)
    now = _at(20)
    game, events = _game(now, appid="9", tags=(1667,), started=now - 5)
    ctx = _ctx(now, game, events=events)
    scene.key(ctx)
    assert scene.script(ctx)[0][0] == "flinch"


def test_care_is_answered_at_once():
    scene = _scene()
    now = _at(16)
    before = scene.key(_ctx(now))
    scene.mind.interact("feed", now)
    ctx = _ctx(now + 1)
    assert scene.key(ctx) != before
    assert scene.script(ctx)[0][0] == "eat"


def test_the_first_window_of_the_morning_says_hello():
    scene = _scene(born=_at(20, day=21))
    scene.mind.observe(_at(23, day=21), night=True, playing=False)
    scene.key(_ctx(_at(23, 30, day=21)))
    scene.mind.observe(_at(8), night=False, playing=False)
    ctx = _ctx(_at(8, 1))
    scene.key(ctx)
    assert scene.script(ctx)[0][0] == "greet"
    later = _ctx(_at(8, 21))
    scene.key(later)
    assert scene.script(later)[0][0] != "greet"


def test_an_evening_of_play_changes_the_panel_only_a_few_times_per_hour():
    scene, rng, changes, previous = _scene(), random.Random(2), 0, None
    start = _at(20)
    game, events = _game(start, tags=(699,), started=start - 900)
    for second in range(0, 3600, 2):
        metrics = {"gpu_temp": 76 + rng.uniform(-6, 6), "fan_pct": 0.6 + rng.uniform(-0.2, 0.2)}
        key = scene.key(_ctx(start + second, game, metrics, events))
        if key != previous:
            changes, previous = changes + 1, key
    assert changes <= pet.PetScene.UPLOADS_PER_HOUR


def test_a_quiet_window_keeps_one_key():
    scene = _scene()
    keys = {scene.key(_ctx(_at(12, m))) for m in range(10)}
    assert len(keys) == 1


def test_life_covers_exactly_until_the_next_window_and_fits():
    scene = _scene()
    ctx = _ctx(_at(12, 7))
    scene.key(ctx)
    segment = scene.render(ctx)
    boundary = _at(12, 10)
    assert segment.valid_until == boundary
    assert sum(segment.delays_cs) == round((boundary - ctx.now) * 100)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


@pytest.mark.parametrize("hours_later", [0, 7, 30])
def test_a_whole_window_of_life_fits_whatever_it_needs(hours_later):
    scene = _scene()
    ctx = _ctx(BORN + hours_later * 3600)
    scene.key(ctx)
    segment = scene.render(ctx)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES
    assert len(scene.script(ctx)) >= 6


def test_a_game_window_fits():
    scene = _scene()
    now = _at(20)
    game, events = _game(now, tags=(1667,), started=now - 5)
    ctx = _ctx(now, game, {"gpu_temp": 60}, events)
    scene.key(ctx)
    assert encoded_size(scene.render(ctx)) <= codec.MAX_GIF_BYTES


def test_something_happens_at_once_and_rests_stay_short():
    scene = _scene()
    ctx = _ctx(_at(12))
    scene.key(ctx)
    script = scene.script(ctx)
    assert script[0][1] < 1
    assert all(rest <= 25 for _, rest in script)
    segment = scene.render(ctx)
    assert max(segment.delays_cs[:-1]) <= 350


def test_every_episode_draws_frames_that_change_and_fit():
    for name in pet.EPISODES:
        frames = pet.episode_frames(name, "idle", {})
        assert len({tuple(c.pixels()) for c, _ in frames}) >= 4, name
        assert len(frames) <= 48, name


def test_every_brain_action_and_reaction_can_be_drawn():
    assert set(pet_mind.ACTIONS) <= set(pet.EPISODES)
    assert set(pet.REACTIONS) <= set(pet.EPISODES)


def test_preview_is_a_montage_of_actions():
    scene = _scene()
    ctx = _ctx(_at(12))
    scene.key(ctx)
    preview = scene.preview(ctx)
    assert len(preview.frames) >= 40
    assert max(preview.delays_cs) <= 10


def test_a_sleeping_loop_for_suspend_fits():
    segment = _scene().asleep({})
    assert len(segment.frames) >= 8
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_its_face_shows_how_it_feels():
    scene = _scene()
    assert scene.face(_ctx(BORN + 600)) is None
    assert scene.face(_ctx(BORN + 30 * 3600)) == "sad"


def test_care_costs_one_write_not_a_second_when_the_reaction_fades():
    scene = _scene()
    now = _at(16, 1)
    scene.mind.interact("pet", now)
    first = scene.key(_ctx(now + 1))
    assert scene.key(_ctx(now + 120)) == first


def test_a_game_start_costs_one_write_not_a_second_when_the_reaction_fades():
    scene = _scene()
    now = _at(20, 1)
    game, events = _game(now, tags=(1667,), started=now - 5)
    first = scene.key(_ctx(now, game, events=events))
    assert scene.key(_ctx(now + 200, game, events=events)) == first


def test_wind_at_home_does_not_flap():
    scene, rng, changes, previous = _scene(), random.Random(5), 0, None
    for second in range(0, 3600, 2):
        key = scene.key(_ctx(_at(12) + second, metrics={"fan_pct": 0.75 + rng.uniform(-0.15, 0.15)}))
        if key != previous:
            changes, previous = changes + 1, key
    assert changes <= pet.PetScene.UPLOADS_PER_HOUR


def _habit(scene, weekday_hour, weeks=3):
    for k in range(weeks):
        t = BORN + k * 7 * 86400
        for s in range(0, 3600, 10):
            scene.mind.observe(t + s, night=False, playing=True, hour_of_week=weekday_hour)


def test_at_your_usual_time_it_waits_and_then_celebrates(tmp_path):
    scene = _scene()
    when = datetime(2026, 11, 12, 21, 0, tzinfo=TZ)
    _habit(scene, when.weekday() * 24 + 21)
    ctx = _ctx(when.timestamp())
    scene.key(ctx)
    assert "await" in {name for name, _ in scene.script(ctx)}
    now = when.timestamp() + 1200
    game, events = _game(now, tags=(19,), started=now - 5)
    ctx = _ctx(now, game, events=events)
    scene.key(ctx)
    assert scene.script(ctx)[0][0] == "excited"
