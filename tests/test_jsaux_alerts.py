import base64

import pytest

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import alerts
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size


def _icon(rgb=(255, 200, 0)):
    return base64.b64encode(bytes(rgb) * (24 * 24)).decode()


@pytest.mark.parametrize("alert", [
    {"kind": "achievement", "title": "Primera sangre", "icon": _icon()},
    {"kind": "achievement", "title": "Un nombre de logro larguísimo que no cabe", "icon": None},
])
def test_alerts_render_as_short_loops_within_size(alert):
    scene = alerts.AlertScene()
    ctx = SceneContext(now=0.0, options={"alert": alert})
    scene.key(ctx)
    segment = scene.render(ctx)
    assert len(segment.frames) >= 6
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_achievement_icon_is_drawn():
    scene = alerts.AlertScene()
    ctx = SceneContext(now=0.0, options={"alert": {"kind": "achievement", "title": "X", "icon": _icon((10, 220, 30))}})
    frame = scene.render(ctx).frames[-1]
    assert any(frame.get(x, y) == (10, 220, 30) for x in range(64) for y in range(54))


def test_download_scene_moves_in_five_percent_steps():
    scene = alerts.DownloadScene()
    keys = set()
    for done in range(0, 1001, 7):
        ctx = SceneContext(now=0.0, events={"download": {"name": "Hades", "done": done, "total": 1000, "seconds": 300}})
        keys.add(scene.key(ctx))
    assert len(keys) <= 22
    assert scene.UPLOADS_PER_HOUR >= 20


def test_download_scene_idle_and_paused_render():
    scene = alerts.DownloadScene()
    for event in (None, {"name": "X", "done": 10, "total": 100, "seconds": 0, "paused": True}):
        ctx = SceneContext(now=0.0, events={"download": event} if event else {})
        scene.key(ctx)
        assert scene.render(ctx).frames
