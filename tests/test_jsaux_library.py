import base64

import pytest

from accessories.jsaux_pixel import codec, library
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.custom import CustomScene
from accessories.jsaux_pixel.scenes.fit import encoded_size

PIXELS = 64 * 54 * 3


def _frame(rgb=(255, 0, 0)):
    return base64.b64encode(bytes(rgb) * (64 * 54)).decode()


def test_save_list_load_and_delete(tmp_path):
    lib = library.Library(tmp_path)
    saved = lib.save({"name": "Corazón", "frames": [_frame(), _frame((0, 255, 0))], "fps": 8})
    items = lib.list()
    assert [item["id"] for item in items] == [saved["id"]]
    assert items[0]["name"] == "Corazón" and items[0]["frames"] == 2 and items[0]["thumb"] == _frame()
    assert lib.load(saved["id"])["fps"] == 8
    lib.delete(saved["id"])
    assert lib.list() == []


def test_updating_keeps_the_same_id(tmp_path):
    lib = library.Library(tmp_path)
    first = lib.save({"name": "A", "frames": [_frame()], "fps": 4})
    second = lib.save({"id": first["id"], "name": "B", "frames": [_frame()], "fps": 4})
    assert second["id"] == first["id"] and [i["name"] for i in lib.list()] == ["B"]


@pytest.mark.parametrize("bad", [
    {"name": "x", "frames": [], "fps": 8},
    {"name": "x", "frames": ["notbase64!!"], "fps": 8},
    {"name": "x", "frames": [base64.b64encode(b"\0" * 10).decode()], "fps": 8},
    {"name": "x", "frames": [_frame()] * (library.MAX_FRAMES + 1), "fps": 8},
    {"name": "x", "frames": [_frame()], "fps": 0},
])
def test_rejects_malformed_drawings(tmp_path, bad):
    with pytest.raises(ValueError):
        library.Library(tmp_path).save(bad)


def test_ids_cannot_escape_the_library(tmp_path):
    lib = library.Library(tmp_path)
    with pytest.raises(ValueError):
        lib.load("../../etc/passwd")
    with pytest.raises(ValueError):
        lib.save({"id": "../x", "name": "x", "frames": [_frame()], "fps": 4})


def test_custom_scene_plays_a_drawing_once_uploaded(tmp_path):
    lib = library.Library(tmp_path)
    saved = lib.save({"name": "A", "frames": [_frame(), _frame((0, 0, 255))], "fps": 5})
    scene = CustomScene(lib)
    ctx = SceneContext(now=0.0, options={"drawing": saved["id"]})
    key = scene.key(ctx)
    assert key == scene.key(SceneContext(now=999999.0, options={"drawing": saved["id"]}))
    segment = scene.render(ctx)
    assert segment.delays_cs == [20, 20]
    assert segment.frames[1].get(0, 0) == (0, 0, 255)
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES
    assert scene.UPLOADS_PER_HOUR == 0


def test_custom_scene_without_a_drawing_is_blank(tmp_path):
    scene = CustomScene(library.Library(tmp_path))
    ctx = SceneContext(now=0.0, options={"drawing": "missing"})
    scene.key(ctx)
    assert scene.render(ctx).frames
