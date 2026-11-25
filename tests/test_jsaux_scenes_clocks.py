from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec, gif
from accessories.jsaux_pixel.render.canvas import quantize
from accessories.jsaux_pixel.scenes import clocks
from accessories.jsaux_pixel.scenes.base import SceneContext

TZ = timezone(timedelta(hours=2))


def _ctx(hour=10, minute=57, second=20):
    now = datetime(2026, 10, 22, hour, minute, second, tzinfo=TZ).timestamp()
    return SceneContext(now=now, tz=TZ)


def _encoded_size(segment):
    palette, indexed = quantize(segment.frames)
    return len(gif.encode([gif.Frame(px, d) for px, d in zip(indexed, segment.delays_cs)], palette))


@pytest.mark.parametrize("scene", clocks.SCENES, ids=lambda s: s.id)
def test_clock_segment_runs_exactly_until_the_next_hour(scene):
    ctx = _ctx(10, 57, 20)
    segment = scene.render(ctx)
    boundary = datetime(2026, 10, 22, 11, 0, tzinfo=TZ).timestamp()
    assert segment.valid_until == boundary
    assert sum(segment.delays_cs) == round((boundary - ctx.now) * 100)
    assert segment.frames


@pytest.mark.parametrize("scene", clocks.SCENES, ids=lambda s: s.id)
def test_a_full_hour_fits_one_upload(scene):
    segment = scene.render(_ctx(10, 0, 1))
    assert _encoded_size(segment) <= codec.MAX_GIF_BYTES
    assert segment.valid_until - _ctx(10, 0, 1).now <= 3600


@pytest.mark.parametrize("scene", clocks.SCENES, ids=lambda s: s.id)
def test_clock_writes_once_per_hour(scene):
    keys = {scene.key(_ctx(10, m, 5)) for m in range(60)}
    assert len(keys) == 1
    assert scene.key(_ctx(11, 0, 5)) not in keys
    assert scene.UPLOADS_PER_HOUR == 1


def test_each_minute_shows_a_different_picture():
    segment = clocks.DigitalClock().render(_ctx(10, 0, 1))
    pixels = [frame.pixels() for frame in segment.frames]
    minute_frames = [p for p in pixels]
    assert len({tuple(p) for p in minute_frames}) >= 60


def test_frame_on_screen_matches_wall_clock():
    scene = clocks.DigitalClock()
    ctx = _ctx(10, 57, 20)
    segment = scene.render(ctx)
    expected = scene.draw(datetime(2026, 10, 22, 10, 58, tzinfo=TZ), {})
    elapsed = 0
    for frame, delay in zip(segment.frames, segment.delays_cs):
        if elapsed >= 4000:
            assert frame.pixels() == expected.pixels()
            break
        elapsed += delay


def test_dates_follow_the_panel_language():
    from accessories.jsaux_pixel.scenes.clocks import long_date, short_date
    from datetime import datetime

    wednesday = datetime(2026, 11, 25, 10, 0, tzinfo=TZ)
    assert long_date(wednesday, {"lang": "es"}) == "MIE 25 NOV"
    assert long_date(wednesday, {"lang": "en"}) == "WED 25 NOV"
    assert short_date(wednesday, {"lang": "de"}) == "MI 25"
    assert long_date(wednesday, {"lang": "pt-BR"}) == "QUA 25 NOV"
    assert long_date(wednesday, {}) == "WED 25 NOV"
