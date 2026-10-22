"""Layouts the user builds from blocks: clock, date, text, live metrics, icons and own drawings.

The layout decides its own write cost: static blocks upload once, a clock or date precomputes the
hour, and metric blocks redraw only when their stepped value moves.
"""

import base64
from datetime import datetime, timedelta

from .. import codec
from ..library import Library
from ..metrics import Stepper
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import THEMES, mix
from .base import Scene, SceneContext, Segment
from .clocks import _DAYS, _MONTHS, _hm, hour_segment

W, H = codec.WIDTH, codec.HEIGHT
MAX_BLOCKS = 20
_TYPES = {"clock", "date", "text", "metric", "icon", "drawing"}
_METRICS = {"cpu_pct": ("CPU", "%"), "gpu_pct": ("GPU", "%"), "ram_pct": ("RAM", "%"), "fps": ("FPS", ""),
            "gpu_w": ("W", ""), "gpu_temp": ("GPU", "°"), "cpu_temp": ("CPU", "°")}
_SIZES = {"s": 0, "m": 1, "l": 2}
_ICONS = {
    "heart": (".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."),
    "star": ("...#...", "..###..", "#######", ".#####.", ".##.##.", "##...##"),
    "pad": (".#####.", "#.###.#", "##.#.##", "#######", "##...##"),
    "bolt": ("...##", "..##.", ".####", "..##.", ".##..", "##..."),
}


def validate_layout(layout: dict) -> list[dict]:
    blocks = layout.get("blocks") if isinstance(layout, dict) else None
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise ValueError("layout needs a list of up to 20 blocks")
    clean = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in _TYPES:
            raise ValueError("unknown block")
        x, y = block.get("x"), block.get("y")
        if not isinstance(x, int) or not isinstance(y, int) or not (-W < x < W and -H < y < H):
            raise ValueError("block outside the display")
        text = str(block.get("text") or "")
        if len(text) > 24:
            raise ValueError("text too long")
        if block["type"] == "metric" and block.get("metric") not in _METRICS:
            raise ValueError("unknown metric")
        if block["type"] == "icon" and block.get("icon") not in _ICONS:
            raise ValueError("unknown icon")
        clean.append({**block, "text": text, "size": block.get("size") if block.get("size") in _SIZES else "m",
                      "color": block.get("color") if block.get("color") in THEMES else "aurora"})
    return clean


class ComposedScene(Scene):
    id = "composed"
    UPLOADS_PER_HOUR = 30
    SETTLE = True

    def __init__(self, library: Library):
        self._library = library
        self._steps: dict[int, Stepper] = {}
        self._values: dict[int, float | None] = {}

    def _blocks(self, ctx: SceneContext) -> list[dict]:
        try:
            return validate_layout(ctx.options.get("layout") or {"blocks": []})
        except ValueError:
            return []

    def key(self, ctx: SceneContext):
        blocks = self._blocks(ctx)
        timed = any(block["type"] in ("clock", "date") for block in blocks)
        hour = datetime.fromtimestamp(ctx.now, ctx.tz).strftime("%Y-%m-%d %H") if timed else None
        values = []
        for index, block in enumerate(blocks):
            if block["type"] == "metric":
                step = self._steps.setdefault(index, Stepper(10 if block["metric"].endswith("pct") or block["metric"] == "fps" else 3, 4))
                raw = ctx.metrics.get(block["metric"])
                self._values[index] = step(raw if isinstance(raw, (int, float)) else None)
                values.append(self._values[index])
        return hour, tuple(values), repr(blocks)

    def render(self, ctx: SceneContext) -> Segment:
        self._art_cache = {}
        blocks = self._blocks(ctx)
        live = any(block["type"] == "metric" for block in blocks)
        if any(block["type"] in ("clock", "date") for block in blocks):
            start = datetime.fromtimestamp(ctx.now, ctx.tz)
            boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment = hour_segment(start, boundary, lambda t: self._draw(blocks, t, ctx.options), lambda a, b: [])
        else:
            segment = Segment([self._draw(blocks, datetime.fromtimestamp(ctx.now, ctx.tz), ctx.options)], [100])
        if live:
            segment.kind, segment.metric = "live", "composed"
        return segment

    def _draw(self, blocks: list[dict], t: datetime, options: dict) -> Canvas:
        canvas = Canvas()
        self._art_cache: dict[str, bytes | None] = getattr(self, "_art_cache", {})
        for index, block in enumerate(blocks):
            theme = THEMES[block["color"]]
            size = _SIZES[block["size"]]
            kind = block["type"]
            if kind == "clock":
                hour, minute = _hm(t, options)
                _gradient(canvas, block["x"], block["y"], f"{hour:02d}:{minute:02d}", (fonts.SMALL, fonts.big(12), fonts.big(18))[size], theme)
            elif kind == "date":
                text = f"{_DAYS[t.weekday()]} {t.day:02d} {_MONTHS[t.month - 1]}"
                canvas.text(block["x"], block["y"], text, (fonts.TINY, fonts.SMALL, fonts.SMALL)[size], theme.soft)
            elif kind == "text":
                _gradient(canvas, block["x"], block["y"], block["text"].upper(), (fonts.TINY, fonts.SMALL, fonts.big(12))[size], theme)
            elif kind == "metric":
                label, suffix = _METRICS[block["metric"]]
                value = self._values.get(index)
                text = f"{label} {'--' if value is None else int(value)}{suffix}"
                _gradient(canvas, block["x"], block["y"], text, (fonts.TINY, fonts.SMALL, fonts.SMALL)[size], theme)
            elif kind == "icon":
                scale_by = size + 1
                for gy, row in enumerate(_ICONS[block["icon"]]):
                    for gx, cell in enumerate(row):
                        if cell == "#":
                            canvas.rect(block["x"] + gx * scale_by, block["y"] + gy * scale_by, scale_by, scale_by,
                                        mix(theme.start, theme.end, gy / len(_ICONS[block["icon"]])))
            elif kind == "drawing":
                self._paste(canvas, block)
        return canvas

    def _paste(self, canvas: Canvas, block: dict) -> None:
        drawing_id = str(block.get("drawing") or "")
        if drawing_id not in self._art_cache:
            try:
                drawing = self._library.load(drawing_id)
            except ValueError:
                drawing = None
            self._art_cache[drawing_id] = base64.b64decode(drawing["frames"][0]) if drawing else None
        raw = self._art_cache[drawing_id]
        if raw is None:
            return
        shrink = (3, 2, 1)[_SIZES[block["size"]]]
        for y in range(0, H, shrink):
            for x in range(0, W, shrink):
                i = (y * W + x) * 3
                rgb = (raw[i], raw[i + 1], raw[i + 2])
                if rgb != (0, 0, 0):
                    canvas.px(block["x"] + x // shrink, block["y"] + y // shrink, rgb)


def _gradient(canvas: Canvas, x: int, y: int, text: str, font: fonts.Font, theme) -> None:
    layer = Canvas()
    layer.text(0, 0, text, font, (255, 255, 255))
    width = max(1, fonts.measure(text, font))
    for py in range(font.height):
        for px in range(min(width, W)):
            if layer.get(px, py) == (255, 255, 255):
                canvas.px(x + px, y + py, mix(theme.start, theme.end, px / width))
