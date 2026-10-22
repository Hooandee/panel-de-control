import base64
import random
from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import game, performance
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))
START = datetime(2026, 10, 22, 18, 20, 5, tzinfo=TZ).timestamp()
GAME = {"appid": "1145360", "name": "Hades", "started_at": START - 1800}


def _metrics(rng, base=1.0):
    return {
        "cpu_pct": 42 + rng.uniform(-4, 4), "gpu_pct": 88 + rng.uniform(-5, 5), "ram_pct": 61 + rng.uniform(-1, 1),
        "fps": 117 + rng.uniform(-6, 6), "gpu_w": 84 + rng.uniform(-4, 4), "gpu_temp": 66 + rng.uniform(-2, 2),
        "cpu_temp": 72 + rng.uniform(-2, 2), "fan_rpm": 1250 + rng.uniform(-60, 60),
    }


def _ctx(now, metrics, game_info=GAME, events=None):
    return SceneContext(now=now, tz=TZ, metrics=metrics, game=game_info, events=events or {})


LIVE = [performance.PowerScene(), performance.HeartScene(), performance.DashboardScene(), game.SessionScene()]


@pytest.mark.parametrize("scene", LIVE, ids=lambda s: s.id)
def test_a_noisy_hour_of_play_stays_within_the_declared_writes(scene):
    rng = random.Random(5)
    keys, previous = 0, object()
    for second in range(0, 3600, 2):
        key = scene.key(_ctx(START + second, _metrics(rng)))
        if key != previous:
            keys += 1
            previous = key
    assert keys <= scene.UPLOADS_PER_HOUR


@pytest.mark.parametrize("scene", LIVE, ids=lambda s: s.id)
def test_live_scene_renders_within_size_and_marks_its_metric(scene):
    ctx = _ctx(START, _metrics(random.Random(1)))
    scene.key(ctx)
    segment = scene.render(ctx)
    assert segment.frames and len(segment.frames) == len(segment.delays_cs)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


@pytest.mark.parametrize("scene", LIVE, ids=lambda s: s.id)
def test_missing_readings_render_without_inventing_numbers(scene):
    ctx = _ctx(START, {}, game_info=None)
    scene.key(ctx)
    assert scene.render(ctx).frames


def test_fan_spins_faster_with_rpm():
    scene = performance.PowerScene()
    slow = _ctx(START, {"fan_rpm": 400})
    fast = _ctx(START, {"fan_rpm": 1700})
    scene.key(slow)
    slow_delay = scene.render(slow).delays_cs[0]
    scene.key(fast)
    fast_delay = scene.render(fast).delays_cs[0]
    assert fast_delay < slow_delay


def test_stopped_fan_is_a_single_still_frame():
    scene = performance.PowerScene()
    ctx = _ctx(START, {"fan_rpm": 0})
    scene.key(ctx)
    assert len(scene.render(ctx).frames) == 1


def test_cover_scene_uses_art_sent_by_the_ui_and_writes_once_per_game():
    scene = game.CoverScene()
    art = base64.b64encode(bytes([120, 40, 200]) * (64 * 54)).decode()
    ctx = _ctx(START, {}, events={"game_art": {"appid": "1145360", "rgb": art}})
    key = scene.key(ctx)
    assert key == scene.key(_ctx(START + 3000, {}, events={"game_art": {"appid": "1145360", "rgb": art}}))
    segment = scene.render(ctx)
    assert segment.frames[0].get(10, 10) != (0, 0, 0)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES
    assert scene.UPLOADS_PER_HOUR <= 2


def test_cover_scene_without_a_game_shows_an_idle_card():
    scene = game.CoverScene()
    ctx = _ctx(START, {}, game_info=None)
    scene.key(ctx)
    assert scene.render(ctx).frames


def _cctx(now, options, events):
    return SceneContext(now=now, tz=TZ, game=GAME, options=options, events=events)


def _cover_events(portrait=True, done=3, total=50, playtime=725):
    events = {
        "game_art": {"appid": "1145360", "rgb": base64.b64encode(bytes([120, 40, 200]) * (64 * 54)).decode()},
        "game_info": {"appid": "1145360", "tags": [], "playtime_min": playtime,
                      "achievements": {"done": done, "total": total} if total else None},
    }
    if portrait:
        events["game_info"]["portrait"] = base64.b64encode(bytes([10, 220, 90]) * (36 * 54)).decode()
    return events


def test_full_cover_is_only_the_art():
    scene = game.CoverScene()
    ctx = _cctx(START, {"layout": "full"}, events=_cover_events())
    scene.key(ctx)
    segment = scene.render(ctx)
    assert len(segment.frames) == 1
    assert {segment.frames[0].get(x, y) for x in range(64) for y in range(54)} == {(120, 40, 200)}


def test_side_cover_shows_the_capsule_and_the_numbers():
    scene = game.CoverScene()
    ctx = _cctx(START, {"layout": "side"}, events=_cover_events())
    scene.key(ctx)
    segment = scene.render(ctx)
    first = segment.frames[0]
    assert first.get(5, 27) == (10, 220, 90)
    assert any(first.get(x, y) != (0, 0, 0) for x in range(38, 64) for y in range(54))
    assert segment.valid_until is not None
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_side_cover_rewrites_when_an_achievement_lands_but_not_every_minute():
    scene = game.CoverScene()
    a = scene.key(_cctx(START, {"layout": "side"}, events=_cover_events(done=3)))
    assert a == scene.key(_cctx(START + 120, {"layout": "side"}, events=_cover_events(done=3)))
    assert a != scene.key(_cctx(START, {"layout": "side"}, events=_cover_events(done=4)))


def test_side_cover_without_a_capsule_crops_the_wide_art_and_skips_missing_numbers():
    scene = game.CoverScene()
    ctx = _cctx(START, {"layout": "side"}, events=_cover_events(portrait=False, total=0, playtime=None))
    scene.key(ctx)
    segment = scene.render(ctx)
    assert segment.frames[0].get(5, 27) == (120, 40, 200)


@pytest.mark.parametrize("minutes,text", [(45, "45 MIN"), (125, "2H 05"), (725, "12 H"), (60_000, "1000 H")])
def test_play_time_reads_naturally(minutes, text):
    assert game.play_time(minutes) == text
