import base64
from datetime import datetime, timedelta, timezone

import pytest

from accessories.jsaux_pixel import codec, library
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.composed import ComposedScene, layout_info, place_free, validate_layout
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
    {"blocks": [{"type": "text", "x": 0, "y": 0, "text": "a"}] * 31},
    {"blocks": [{"type": "sticker", "x": 0, "y": 0, "sticker": "nuke"}]},
    {"blocks": [{"type": "text", "x": 0, "y": 0, "text": "a", "font": "comic"}]},
    {"blocks": [{"type": "text", "x": 0, "y": 0, "text": "a", "rot": 45}]},
])
def test_invalid_layouts_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_layout(bad)


def test_empty_layout_renders_blank(scene):
    scene.key(_ctx([]))
    assert scene.render(_ctx([])).frames


def _sticker(name, x=10, y=10, **extra):
    return {"type": "sticker", "x": x, "y": y, "size": "m", "sticker": name, "color": "aurora", **extra}


def test_a_still_sticker_is_one_frame_forever(scene):
    blocks = [_sticker("star")]
    scene.key(_ctx(blocks))
    segment = scene.render(_ctx(blocks))
    assert len(segment.frames) == 1 and segment.valid_until is None


def test_animated_stickers_loop_inside_one_upload(scene):
    blocks = [_sticker("fire"), _sticker("coin", x=30)]
    scene.key(_ctx(blocks))
    segment = scene.render(_ctx(blocks))
    assert len({tuple(f.pixels()) for f in segment.frames}) >= 3
    assert segment.valid_until is None
    assert layout_info(validate_layout({"blocks": blocks}))["mode"] == "animated"


def test_a_clock_with_stickers_animates_once_a_minute_and_fits(scene):
    blocks = [{"type": "clock", "x": 2, "y": 2, "size": "l", "color": "mint"}, _sticker("sparkle", x=50, y=40)]
    scene.key(_ctx(blocks))
    segment = scene.render(_ctx(blocks))
    assert len(segment.frames) > 60
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES
    assert layout_info(validate_layout({"blocks": blocks}))["mode"] == "clock"


def test_rotation_turns_the_block_box():
    blocks = validate_layout({"blocks": [{"type": "text", "x": 0, "y": 0, "text": "HOLA", "font": "small"},
                                         {"type": "text", "x": 0, "y": 20, "text": "HOLA", "font": "small", "rot": 90}]})
    flat, turned = layout_info(blocks)["boxes"]
    assert (flat["w"], flat["h"]) == (turned["h"], turned["w"])


def test_pills_paint_a_capsule_behind_the_text(scene):
    blocks = [{"type": "pill", "x": 4, "y": 4, "text": "GG", "color": "sunset", "font": "small"}]
    scene.key(_ctx(blocks))
    frame = scene.render(_ctx(blocks)).frames[0]
    box = layout_info(validate_layout({"blocks": blocks}))["boxes"][0]
    assert frame.get(4 + box["w"] // 2, 4) != (0, 0, 0)
    assert frame.get(4, 4) == (0, 0, 0)


@pytest.mark.parametrize("font", ["tiny", "small", "bold", "big", "outline", "shadow"])
def test_every_font_draws(scene, font):
    blocks = [{"type": "text", "x": 1, "y": 1, "text": "PIXEL 7", "font": font}]
    scene.key(_ctx(blocks))
    frame = scene.render(_ctx(blocks)).frames[0]
    assert sum(1 for p in frame.pixels() if p != (0, 0, 0)) > 20


def test_fonts_look_different():
    widths = {font: layout_info(validate_layout({"blocks": [{"type": "text", "x": 0, "y": 0, "text": "AB", "font": font}]}))["boxes"][0]["w"]
              for font in ("tiny", "small", "big")}
    assert widths["tiny"] < widths["small"] < widths["big"]


def test_a_new_piece_drops_into_the_first_free_gap():
    blocks = validate_layout({"blocks": [{"type": "pill", "x": 0, "y": 0, "text": "GG"}, _sticker("star", x=0, y=0)]})
    placed = place_free(blocks, 1)
    boxes = layout_info(placed)["boxes"]
    a, b = boxes
    overlap = a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]
    assert not overlap
    assert placed[0] == blocks[0]


def test_layout_info_reads_the_refresh_mode():
    assert layout_info(validate_layout({"blocks": [_sticker("star")]}))["mode"] == "static"
    live = [{"type": "metric", "x": 0, "y": 0, "metric": "fps"}]
    assert layout_info(validate_layout({"blocks": live}))["mode"] == "live"


def test_an_animated_drawing_moves_as_a_sticker(tmp_path):
    lib = library.Library(tmp_path)
    frames = [base64.b64encode(bytes([c, 0, 0]) * (64 * 54)).decode() for c in (90, 180)]
    saved = lib.save({"name": "x", "frames": frames, "fps": 4})
    scene = ComposedScene(lib)
    blocks = [{"type": "drawing", "x": 0, "y": 0, "size": "s", "drawing": saved["id"]}]
    scene.key(_ctx(blocks))
    segment = scene.render(_ctx(blocks))
    assert {segment.frames[i].get(0, 0) for i in range(len(segment.frames))} == {(90, 0, 0), (180, 0, 0)}
