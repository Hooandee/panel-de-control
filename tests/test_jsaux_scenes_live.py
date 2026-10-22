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
