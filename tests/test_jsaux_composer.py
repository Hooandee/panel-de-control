import base64
from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec, library
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.composed import ComposedScene, validate_layout
from accessories.jsaux_pixel.scenes.fit import encoded_size

TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 10, 22, 21, 15, 30, tzinfo=TZ).timestamp()


def _ctx(blocks, metrics=None, now=NOW):
    return SceneContext(now=now, tz=TZ, options={"layout": {"blocks": blocks}}, metrics=metrics or {})


@pytest.fixture
def scene(tmp_path):
    return ComposedScene(library.Library(tmp_path))


def test_static_layout_is_one_upload_forever(scene):
    blocks = [{"type": "text", "x": 2, "y": 2, "size": "m", "text": "HOLA", "color": "aurora"},
              {"type": "icon", "x": 40, "y": 30, "size": "l", "icon": "heart", "color": "sunset"}]
    key = scene.key(_ctx(blocks))
    assert key == scene.key(_ctx(blocks, now=NOW + 86400))
    segment = scene.render(_ctx(blocks))
    assert segment.valid_until is None and len(segment.frames) == 1


def test_clock_block_precomputes_the_hour(scene):
    blocks = [{"type": "clock", "x": 4, "y": 10, "size": "l", "color": "mint"}]
    scene.key(_ctx(blocks))
    segment = scene.render(_ctx(blocks))
    boundary = datetime(2026, 10, 22, 22, 0, tzinfo=TZ).timestamp()
    assert segment.valid_until == boundary
    assert sum(segment.delays_cs) == round((boundary - NOW) * 100)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_metric_block_moves_in_steps(scene):
    blocks = [{"type": "metric", "x": 2, "y": 2, "size": "m", "metric": "gpu_pct", "color": "aurora"}]
    first = scene.key(_ctx(blocks, {"gpu_pct": 61}))
    assert scene.key(_ctx(blocks, {"gpu_pct": 64})) == first
    assert scene.key(_ctx(blocks, {"gpu_pct": 76})) != first
    assert scene.render(_ctx(blocks, {"gpu_pct": 76})).kind == "live"


def test_drawing_block_places_the_users_art(tmp_path):
    lib = library.Library(tmp_path)
    saved = lib.save({"name": "x", "frames": [base64.b64encode(bytes([0, 200, 0]) * (64 * 54)).decode()], "fps": 4})
    scene = ComposedScene(lib)
    blocks = [{"type": "drawing", "x": 10, "y": 5, "size": "s", "drawing": saved["id"]}]
    scene.key(_ctx(blocks))
    frame = scene.render(_ctx(blocks)).frames[0]
    assert frame.get(10, 5) == (0, 200, 0)
    assert frame.get(0, 0) == (0, 0, 0)


@pytest.mark.parametrize("bad", [
    {"blocks": "x"},
    {"blocks": [{"type": "nope", "x": 0, "y": 0}]},
    {"blocks": [{"type": "text", "x": 999, "y": 0, "text": "a"}]},
    {"blocks": [{"type": "text", "x": 0, "y": 0, "text": "a" * 200}]},
    {"blocks": [{"type": "metric", "x": 0, "y": 0, "metric": "evil"}]},
    {"blocks": [{"type": "text", "x": 0, "y": 0, "text": "a"}] * 21},
])
def test_invalid_layouts_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_layout(bad)


def test_empty_layout_renders_blank(scene):
    scene.key(_ctx([]))
    assert scene.render(_ctx([])).frames
