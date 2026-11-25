from datetime import timedelta, timezone

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import speedrun
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))
NOW = 1_800_000_000.0
GAME = {"appid": "1", "name": "Celeste", "started_at": NOW - 125}


def _ctx(now, game=GAME, run=None, options=None):
    return SceneContext(now=now, tz=TZ, game=game, events={"speedrun": run} if run else {}, options=options or {})


def test_the_timer_starts_with_the_game_and_ticks_every_second_inside_one_upload():
    scene = speedrun.SpeedrunScene()
    ctx = _ctx(NOW)
    scene.key(ctx)
    segment = scene.render(ctx)
    assert segment.valid_until is not None and segment.valid_until > NOW
    covered = round((segment.valid_until - NOW) * 100)
    assert sum(segment.delays_cs) == covered
    assert covered >= 300 * 100
    assert len(segment.frames) >= covered // 100 - 1
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_one_key_per_window_so_it_writes_a_few_times_an_hour():
    scene = speedrun.SpeedrunScene()
    keys = {scene.key(_ctx(NOW + s)) for s in range(0, 3600, 5)}
    assert len(keys) <= speedrun.SpeedrunScene.UPLOADS_PER_HOUR


def test_reset_restarts_from_zero():
    scene = speedrun.SpeedrunScene()
    before = scene.key(_ctx(NOW))
    run = {"origin": NOW, "paused_at": None}
    assert scene.key(_ctx(NOW, run=run)) != before
    assert speedrun.elapsed(_ctx(NOW + 61, run=run)) == 61


def test_a_paused_run_is_one_still_image():
    scene = speedrun.SpeedrunScene()
    ctx = _ctx(NOW, run={"origin": NOW - 3725, "paused_at": NOW - 5})
    scene.key(ctx)
    segment = scene.render(ctx)
    assert segment.valid_until is None
    assert len(segment.frames) <= 2
    assert speedrun.elapsed(ctx) == 3720


def test_without_a_game_it_waits_for_the_start():
    scene = speedrun.SpeedrunScene()
    ctx = _ctx(NOW, game=None)
    scene.key(ctx)
    assert scene.render(ctx).valid_until is None


def test_formats_like_a_speedrun_timer():
    assert speedrun.clock_text(5) == "0:05"
    assert speedrun.clock_text(754) == "12:34"
    assert speedrun.clock_text(3725) == "1:02:05"


def test_past_an_hour_still_fits():
    scene = speedrun.SpeedrunScene()
    ctx = _ctx(NOW, game={**GAME, "started_at": NOW - 4000})
    scene.key(ctx)
    assert encoded_size(scene.render(ctx)) <= codec.MAX_GIF_BYTES
