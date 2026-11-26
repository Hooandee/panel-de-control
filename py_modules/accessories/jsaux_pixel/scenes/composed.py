"""Layouts the user builds from pieces: text in several fonts, pills, stickers, own drawings,
clock, date and live metrics, each one movable and rotatable.

The pieces decide the write cost: a still layout is written once; animated stickers loop inside
that single write; a clock or date precomputes the hour (stickers wiggle once a minute inside
it); metrics redraw only when their stepped value moves.
"""

import base64
import math
from datetime import datetime, timedelta

from .. import codec
from ..library import Library
from ..metrics import Stepper
from ..render import fonts, stickers
from ..render.canvas import Canvas
from ..render.palettes import THEMES, mix, scale
from ..render.text import plain_text
from .base import Scene, SceneContext, Segment
from .clocks import _hm, hour_segment, long_date
from .fit import fits

W, H = codec.WIDTH, codec.HEIGHT
MAX_BLOCKS = 30
FONTS = ("tiny", "small", "bold", "big", "outline", "shadow")
ROTATIONS = (0, 90, 180, 270)
_TYPES = {"clock", "date", "text", "metric", "icon", "drawing", "pill", "sticker"}
_METRICS = {"cpu_pct": ("CPU", "%"), "gpu_pct": ("GPU", "%"), "ram_pct": ("RAM", "%"), "fps": ("FPS", ""),
            "gpu_w": ("W", ""), "gpu_temp": ("GPU", "°"), "cpu_temp": ("CPU", "°")}
_SIZES = {"s": 0, "m": 1, "l": 2}
_ICONS = {
    "heart": (".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."),
    "star": ("...#...", "..###..", "#######", ".#####.", ".##.##.", "##...##"),
    "pad": (".#####.", "#.###.#", "##.#.##", "#######", "##...##"),
    "bolt": ("...##", "..##.", ".####", "..##.", ".##..", "##..."),
}
_ANIM_CS = 15
_WIDEST_TIME = datetime(2026, 1, 3, 20, 28)
_MAX_ANIM_FRAMES = 12
_INK = (20, 16, 30)


def validate_layout(layout: dict) -> list[dict]:
    blocks = layout.get("blocks") if isinstance(layout, dict) else None
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise ValueError("layout needs a list of up to 30 blocks")
    clean = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in _TYPES:
            raise ValueError("unknown block")
        x, y = block.get("x"), block.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("block outside the display")
        # A stored layout must never blank the whole panel over one piece pushed off the edge.
        x, y = max(1 - W, min(W - 1, x)), max(1 - H, min(H - 1, y))
        text = str(block.get("text") or "")
        if len(text) > 24:
            raise ValueError("text too long")
        if block["type"] == "metric" and block.get("metric") not in _METRICS:
            raise ValueError("unknown metric")
        if block["type"] == "icon" and block.get("icon") not in _ICONS:
            raise ValueError("unknown icon")
        if block["type"] == "sticker" and block.get("sticker") not in stickers.STICKERS:
            raise ValueError("unknown sticker")
        if "font" in block and block["font"] not in FONTS:
            raise ValueError("unknown font")
        rot = block.get("rot", 0)
        if rot not in ROTATIONS:
            raise ValueError("rotation must be a quarter turn")
        size = block.get("size") if block.get("size") in _SIZES else "m"
        colour = block.get("color")
        if colour not in THEMES and not (colour == "original" and block["type"] == "sticker"):
            colour = "original" if block["type"] == "sticker" else "aurora"
        clean.append({**block, "x": x, "y": y, "text": text, "size": size, "rot": rot, "font": block.get("font") or _default_font(block["type"], size),
                      "color": colour})
    return clean


def _default_font(kind: str, size: str) -> str:
    if kind == "clock":
        return "small" if size == "s" else "big"
    if kind in ("date", "metric"):
        return "tiny" if size == "s" else "small"
    return ("tiny", "small", "big")[_SIZES[size]]


def _font(name: str) -> fonts.Font:
    return fonts.TINY if name == "tiny" else fonts.SMALL


def text_sprite(text: str, font: str, theme, solid=None) -> Canvas:
    base = _font(font)
    width = max(1, fonts.measure(text, base))
    pad = 1 if font in ("outline", "shadow", "bold") else 0
    zoom = 2 if font == "big" else 1
    mask = Canvas(width + pad * 2 + (1 if font == "bold" else 0), base.height + pad * 2)
    mask.text(pad, pad, text, base, (255, 255, 255))
    if font == "bold":
        mask.text(pad + 1, pad, text, base, (255, 255, 255))
    out = Canvas(mask.width * zoom, mask.height * zoom)

    def paint(x: int, y: int) -> tuple:
        return solid or mix(theme.start, theme.end, x / max(1, out.width - 1))

    for y in range(mask.height):
        for x in range(mask.width):
            if mask.get(x, y) == (255, 255, 255):
                out.rect(x * zoom, y * zoom, zoom, zoom, paint(x * zoom, y * zoom))
            elif font == "outline" and _touches(mask, x, y):
                out.rect(x * zoom, y * zoom, zoom, zoom, (255, 255, 255))
            elif font == "shadow" and 0 < x and 0 < y and mask.get(x - 1, y - 1) == (255, 255, 255):
                out.rect(x * zoom, y * zoom, zoom, zoom, scale(theme.end, 0.35))
    return out


def _touches(mask: Canvas, x: int, y: int) -> bool:
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < mask.width and 0 <= ny < mask.height and mask.get(nx, ny) == (255, 255, 255):
            return True
    return False


def rotate(canvas: Canvas, rot: int) -> Canvas:
    if rot == 0:
        return canvas
    turns = rot // 90
    out = canvas
    for _ in range(turns):
        turned = Canvas(out.height, out.width)
        for y in range(out.height):
            for x in range(out.width):
                turned.px(out.height - 1 - y, x, out.get(x, y))
        out = turned
    return out


def _pill(text: str, font: str, theme) -> Canvas:
    label = text_sprite(text or " ", "tiny" if font == "tiny" else "small", theme, solid=_INK)
    width, height = label.width + 8, label.height + 4
    out = Canvas(width, height)
    radius = height // 2
    for y in range(height):
        for x in range(width):
            dx = max(radius - x, x - (width - 1 - radius), 0)
            dy = y - (height - 1) / 2
            if dx * dx + dy * dy <= radius * radius + 0.5:
                out.px(x, y, mix(theme.start, theme.end, x / max(1, width - 1)))
    out.blit(label, 4, 2)
    return out


def _frame_count(block: dict, library: Library | None, cache: dict) -> int:
    if block["type"] == "sticker":
        return len(stickers.frames_of(block["sticker"]))
    if block["type"] == "drawing":
        return len(_drawing_frames(block, library, cache) or [b""])
    return 1


def _drawing_frames(block: dict, library: Library | None, cache: dict) -> list[bytes] | None:
    drawing_id = str(block.get("drawing") or "")
    if drawing_id not in cache:
        drawing = None
        if library is not None:
            try:
                drawing = library.load(drawing_id)
            except ValueError:
                drawing = None
        cache[drawing_id] = [base64.b64decode(f) for f in drawing["frames"]] if drawing else None
    return cache[drawing_id]


def layout_info(blocks: list[dict], library: Library | None = None) -> dict:
    """Where each piece sits and how often the layout needs writing, for the editor."""
    cache: dict = {}
    boxes = []
    for block in blocks:
        sprite = _sprite(block, _WIDEST_TIME, {}, library, cache, 0, measuring=True)
        boxes.append({"x": block["x"], "y": block["y"], "w": sprite.width, "h": sprite.height})
    return {"boxes": boxes, "mode": refresh_mode(blocks, library, cache)}


def refresh_mode(blocks: list[dict], library: Library | None = None, cache: dict | None = None) -> str:
    cache = {} if cache is None else cache
    kinds = {block["type"] for block in blocks}
    if "metric" in kinds:
        return "live"
    if kinds & {"clock", "date"}:
        return "clock"
    if any(_frame_count(block, library, cache) > 1 for block in blocks):
        return "animated"
    return "static"


def place_free(blocks: list[dict], index: int, library: Library | None = None) -> list[dict]:
    """Drops blocks[index] into the first gap, top to bottom and left to right, like a falling piece."""
    boxes = layout_info(blocks, library)["boxes"]
    mine = boxes[index]
    others = [box for i, box in enumerate(boxes) if i != index]
    for y in range(0, max(1, H - mine["h"] + 1)):
        for x in range(0, max(1, W - mine["w"] + 1)):
            if not any(x < o["x"] + o["w"] + 1 and o["x"] < x + mine["w"] + 1 and
                       y < o["y"] + o["h"] + 1 and o["y"] < y + mine["h"] + 1 for o in others):
                return [{**block, "x": x, "y": y} if i == index else block for i, block in enumerate(blocks)]
    return blocks


def _sprite(block: dict, t: datetime, values: dict, library: Library | None, cache: dict, frame: int,
            options: dict | None = None, measuring: bool = False) -> Canvas:
    theme = THEMES.get(block["color"], THEMES["aurora"])
    kind = block["type"]
    font = block["font"]
    if kind == "clock":
        hour, minute = _hm(t, options or {})
        text = f"{hour:02d}:{minute:02d}"
        if font == "big":
            digits = fonts.big((10, 12, 18)[_SIZES[block["size"]]])
            mask = Canvas(fonts.measure(text, digits), digits.height)
            mask.text(0, 0, text, digits, (255, 255, 255))
            sprite = _gradient(mask, theme)
        else:
            sprite = text_sprite(text, font, theme)
    elif kind == "date":
        sprite = text_sprite(long_date(t, options), font, theme)
    elif kind == "text":
        sprite = text_sprite(plain_text(block["text"]) or " ", font, theme)
    elif kind == "pill":
        sprite = _pill(plain_text(block["text"]) or " ", font, theme)
    elif kind == "metric":
        label, suffix = _METRICS[block["metric"]]
        value = values.get(id(block))
        shown = "100" if measuring else "--" if value is None else str(int(value))
        sprite = text_sprite(f"{label} {shown}{suffix}", font, theme)
    elif kind == "icon":
        zoom = _SIZES[block["size"]] + 1
        rows = _ICONS[block["icon"]]
        sprite = Canvas(len(rows[0]) * zoom, len(rows) * zoom)
        for gy, row in enumerate(rows):
            for gx, cell in enumerate(row):
                if cell == "#":
                    sprite.rect(gx * zoom, gy * zoom, zoom, zoom, mix(theme.start, theme.end, gy / len(rows)))
    elif kind == "sticker":
        zoom = _SIZES[block["size"]] + 1
        tint = None if block["color"] == "original" else theme.start
        sprite = stickers.sprite(block["sticker"], frame, zoom, tint)
    else:
        sprite = _drawing_sprite(block, library, cache, frame)
    return rotate(sprite, block["rot"])


def _gradient(mask: Canvas, theme) -> Canvas:
    out = Canvas(mask.width, mask.height)
    for y in range(mask.height):
        for x in range(mask.width):
            if mask.get(x, y) != (0, 0, 0):
                out.px(x, y, mix(theme.start, theme.end, x / max(1, mask.width - 1)))
    return out


def _drawing_sprite(block: dict, library: Library | None, cache: dict, frame: int) -> Canvas:
    shrink = (3, 2, 1)[_SIZES[block["size"]]]
    out = Canvas(math.ceil(W / shrink), math.ceil(H / shrink))
    frames = _drawing_frames(block, library, cache)
    if not frames:
        return out
    raw = frames[frame % len(frames)]
    for y in range(0, H, shrink):
        for x in range(0, W, shrink):
            i = (y * W + x) * 3
            out.px(x // shrink, y // shrink, (raw[i], raw[i + 1], raw[i + 2]))
    return out


class ComposedScene(Scene):
    id = "composed"
    UPLOADS_PER_HOUR = 30
    SETTLE = True

    def __init__(self, library: Library):
        self._library = library
        self._steps: dict[tuple[int, str], Stepper] = {}
        self._values: dict[tuple[int, str], float | None] = {}

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
                # Keyed by the metric too: the same piece slot can hold another reading in the game
                # layout or after an edit, and must not inherit its steps.
                slot = (index, block["metric"])
                step = self._steps.setdefault(slot, Stepper(10 if block["metric"].endswith("pct") or block["metric"] == "fps" else 3, 4))
                raw = ctx.metrics.get(block["metric"])
                self._values[slot] = step(raw if isinstance(raw, (int, float)) else None)
                values.append(self._values[slot])
        return hour, tuple(values), repr(blocks)

    def render(self, ctx: SceneContext) -> Segment:
        blocks = self._blocks(ctx)
        cache: dict = {}
        values = {id(block): self._values.get((index, block["metric"])) for index, block in enumerate(blocks) if block["type"] == "metric"}
        mode = refresh_mode(blocks, self._library, cache)
        cycle = _cycle(blocks, self._library, cache)

        def draw(t: datetime, frame: int = 0) -> Canvas:
            canvas = Canvas()
            for block in blocks:
                canvas.blit(_sprite(block, t, values, self._library, cache, frame, ctx.options), block["x"], block["y"])
            return canvas

        now = datetime.fromtimestamp(ctx.now, ctx.tz)
        if mode == "clock" or mode == "live" and any(block["type"] in ("clock", "date") for block in blocks):
            # A clock next to a metric still gets its hour of minutes; the metric only rewrites it
            # when its reading steps, within the live gap.
            boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            repeats = max(1, 90 // max(1, cycle * 6)) if cycle > 1 else 0

            def wiggle(_previous: datetime, minute: datetime) -> list[Canvas]:
                return [draw(minute, frame) for _ in range(repeats) for frame in range(cycle)]

            segment = hour_segment(now, boundary, draw, wiggle if cycle > 1 else (lambda a, b: []))
            if mode == "live":
                segment.kind, segment.metric = "live", "composed"
            return segment
        while True:
            frames = [draw(now, frame) for frame in range(cycle)]
            segment = Segment(frames, [_ANIM_CS if cycle > 1 else 100] * len(frames))
            if cycle == 1 or fits(segment):
                break
            cycle //= 2
        if mode == "live":
            segment.kind, segment.metric = "live", "composed"
        return segment


def _cycle(blocks: list[dict], library: Library | None, cache: dict) -> int:
    lengths = {_frame_count(block, library, cache) for block in blocks} - {1}
    cycle = 1
    for length in lengths:
        cycle = cycle * length // math.gcd(cycle, length)
    return min(cycle, _MAX_ANIM_FRAMES)
