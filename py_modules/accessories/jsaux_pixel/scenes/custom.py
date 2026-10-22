"""Plays one of the user's drawings: a single upload, then the panel loops it."""

import base64

from ..library import Library
from ..render.canvas import Canvas
from .base import Scene, SceneContext, Segment


class CustomScene(Scene):
    id = "custom"
    UPLOADS_PER_HOUR = 0

    def __init__(self, library: Library):
        self._library = library

    def _drawing(self, ctx: SceneContext) -> dict | None:
        try:
            return self._library.load(str(ctx.options.get("drawing") or ""))
        except ValueError:
            return None

    def key(self, ctx: SceneContext):
        drawing = self._drawing(ctx)
        return (drawing or {}).get("id"), (drawing or {}).get("updated")

    def render(self, ctx: SceneContext) -> Segment:
        drawing = self._drawing(ctx)
        if not drawing:
            return Segment([Canvas()], [100])
        frames = []
        for encoded in drawing["frames"]:
            raw = base64.b64decode(encoded)
            canvas = Canvas()
            for index in range(64 * 54):
                r, g, b = raw[index * 3:index * 3 + 3]
                if r or g or b:
                    canvas.px(index % 64, index // 64, (r, g, b))
            frames.append(canvas)
        delay = max(3, round(100 / int(drawing.get("fps") or 8)))
        return Segment(frames, [delay] * len(frames))
