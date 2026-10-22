import pytest

from accessories.jsaux_pixel import codec
from accessories.jsaux_pixel.scenes import art
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

CTX = SceneContext(now=1_700_000_000.0)


@pytest.mark.parametrize("scene", art.SCENES, ids=lambda s: s.id)
def test_art_is_one_upload_that_loops_forever(scene):
    segment = scene.render(CTX)
    assert segment.valid_until is None
    assert scene.UPLOADS_PER_HOUR == 0
    assert scene.key(CTX) == scene.key(SceneContext(now=CTX.now + 86400))
    assert len(segment.frames) >= 12
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


@pytest.mark.parametrize("scene", [s for s in art.SCENES if s.seamless], ids=lambda s: s.id)
def test_loops_close_without_a_jump(scene):
    segment = scene.render(CTX)
    first, last = segment.frames[0].pixels(), segment.frames[-1].pixels()
    after_last = scene.frame(len(segment.frames), len(segment.frames), CTX.options).pixels()
    assert after_last == first
    assert last != first


@pytest.mark.parametrize("scene", art.SCENES, ids=lambda s: s.id)
def test_art_is_never_brighter_than_the_light_budget_needs(scene):
    from accessories.jsaux_pixel import power_guard
    from accessories.jsaux_pixel.gif import Frame
    from accessories.jsaux_pixel.render.canvas import quantize
    palette, indexed = quantize(scene.render(CTX).frames)
    peak = max(power_guard.frame_load(palette, Frame(px, 1)) for px in indexed)
    assert peak <= power_guard.LIGHT_BUDGET
