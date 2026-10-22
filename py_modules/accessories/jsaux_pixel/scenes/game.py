"""Scenes about the game being played."""

import base64
import hashlib
import json
from datetime import datetime, timedelta

from .. import codec
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .clocks import _centered, hour_segment

W, H = codec.WIDTH, codec.HEIGHT
_ART_BYTES = W * H * 3
_PORTRAIT_W = 36


def _title(game: dict | None) -> str:
    name = (game or {}).get("name") or ""
    return "".join(ch for ch in name.upper() if ch.isalnum() or ch in " :-'!?.") or "STEAM"


class SessionScene(Scene):
    """Time in the current game, precomputed an hour ahead like the clocks."""

    id = "game_session"
    OPTIONS = ("theme",)
    UPLOADS_PER_HOUR = 2

    def key(self, ctx: SceneContext):
        t = datetime.fromtimestamp(ctx.now, ctx.tz)
        game = ctx.game or {}
        return t.strftime("%Y-%m-%d %H"), game.get("appid"), game.get("started_at"), ctx.options.get("theme")

    def render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        game = ctx.game
        start = datetime.fromtimestamp(ctx.now, ctx.tz)
        boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        began = (game or {}).get("started_at")

        def draw(t: datetime) -> Canvas:
            canvas = Canvas()
            title = _title(game)
            shown = title if fonts.measure(title, fonts.TINY) <= W - 2 else title[: max(1, (W - 6) // 4)].rstrip() + "."
            _centered(canvas, 3, shown, fonts.TINY, theme.soft)
            if game and isinstance(began, (int, float)):
                minutes = max(0, int((t.timestamp() - began) // 60))
                text = f"{minutes // 60}:{minutes % 60:02d}"
                _centered(canvas, 15, text, fonts.big(18), theme.start)
                _centered(canvas, 38, "EN PARTIDA" if ctx.options.get("lang", "es") == "es" else "PLAYING", fonts.TINY, theme.soft)
                hour_progress = (minutes % 60) / 60
                for i in range(56):
                    canvas.px(4 + i, 47, mix(theme.start, theme.end, i / 55) if i < round(56 * hour_progress) else theme.dim)
            else:
                _centered(canvas, 18, "--:--", fonts.big(14), theme.dim)
                _centered(canvas, 38, "STEAM", fonts.TINY, theme.soft)
            return canvas

        return hour_segment(start, boundary, draw, lambda a, b: [])


class CoverScene(Scene):
    """The game's art, reduced by the UI. "full" fills the display with it and is written once
    per game; "side" puts the capsule on the left and the name, total play time and achievements
    on the right, precomputed an hour ahead so play time ticks without extra writes."""

    id = "game_cover"
    UPLOADS_PER_HOUR = 2
    OPTIONS = ("layout", "theme")

    def key(self, ctx: SceneContext):
        art = self._art(ctx)
        digest = hashlib.sha1(art).hexdigest() if art else None
        if ctx.options.get("layout") != "side":
            return (ctx.game or {}).get("appid"), digest
        info = self._info(ctx)
        hour = datetime.fromtimestamp(ctx.now, ctx.tz).strftime("%Y-%m-%d %H")
        portrait = hashlib.sha1(info.get("portrait", "").encode()).hexdigest()[:12]
        return (ctx.game or {}).get("appid"), digest, hour, portrait, json.dumps(info.get("achievements")), info.get("playtime_min")

    def _art(self, ctx: SceneContext) -> bytes | None:
        event = ctx.events.get("game_art") if isinstance(ctx.events, dict) else None
        if not isinstance(event, dict):
            return None
        appid = (ctx.game or {}).get("appid")
        if appid is not None and str(event.get("appid")) != str(appid):
            return None
        return _decoded(event.get("rgb"), _ART_BYTES)

    def _info(self, ctx: SceneContext) -> dict:
        info = ctx.events.get("game_info") if isinstance(ctx.events, dict) else None
        appid = (ctx.game or {}).get("appid")
        if not isinstance(info, dict) or str(info.get("appid")) != str(appid):
            return {}
        return info

    def render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        art = self._art(ctx)
        if ctx.options.get("layout") == "side" and ctx.game:
            return self._side(ctx, art, theme)
        base = Canvas()
        if art:
            _paint(base, art, 0, W, 0)
        else:
            _controller(base, theme)
            _centered(base, H - 8, _title(ctx.game) if ctx.game else "STEAM", fonts.SMALL, theme.soft)
        return Segment([base], [100])

    def _side(self, ctx: SceneContext, art: bytes | None, theme) -> Segment:
        info = self._info(ctx)
        base = Canvas()
        portrait = _decoded(info.get("portrait"), _PORTRAIT_W * H * 3)
        if portrait:
            _paint(base, portrait, 0, _PORTRAIT_W, 0)
        elif art:
            _paint(base, art, 0, _PORTRAIT_W, (W - _PORTRAIT_W) // 2, source_width=W)
        else:
            base.rect(0, 0, _PORTRAIT_W, H, theme.dim)
        for y in range(H):
            base.px(_PORTRAIT_W, y, scale(theme.start, 0.5))
        right = _PORTRAIT_W + 3
        lines = _wrap(_title(ctx.game), W - right - 1, 3)
        for i, line in enumerate(lines):
            base.text(right, 2 + i * 7, line, fonts.TINY, (255, 255, 255))
        achievements = info.get("achievements") if isinstance(info.get("achievements"), dict) else None
        if achievements:
            _trophy(base, right, 45)
            base.text(right + 7, 46, f"{achievements['done']}/{achievements['total']}", fonts.TINY, theme.soft)
        played = info.get("playtime_min")
        began = (ctx.game or {}).get("started_at")
        if not isinstance(played, (int, float)):
            return Segment([base], [100])
        start = datetime.fromtimestamp(ctx.now, ctx.tz)
        boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        sent_at = info.get("sent_at") if isinstance(info.get("sent_at"), (int, float)) else began

        def draw(t: datetime) -> Canvas:
            frame = base.copy()
            extra = max(0, int((t.timestamp() - sent_at) // 60)) if isinstance(sent_at, (int, float)) else 0
            _clock_icon(frame, right, 34, theme)
            frame.text(right + 7, 35, play_time(int(played) + extra), fonts.TINY, theme.start)
            return frame

        return hour_segment(start, boundary, draw, lambda a, b: [])


def play_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} MIN"
    if minutes < 600:
        return f"{minutes // 60}H {minutes % 60:02d}"
    return f"{minutes // 60} H"


def _decoded(value, size: int) -> bytes | None:
    try:
        raw = base64.b64decode(value or "", validate=True)
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == size else None


def _paint(canvas: Canvas, rgb: bytes, x0: int, width: int, offset: int, source_width: int | None = None) -> None:
    stride = source_width or width
    for y in range(H):
        for x in range(width):
            i = (y * stride + x + offset) * 3
            canvas.px(x0 + x, y, (rgb[i], rgb[i + 1], rgb[i + 2]))


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and fonts.measure(f"{lines[-1]} {word}", fonts.TINY) <= width:
            lines[-1] = f"{lines[-1]} {word}"
            continue
        while fonts.measure(word, fonts.TINY) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and fonts.measure(word[:cut], fonts.TINY) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and fonts.measure(last + ".", fonts.TINY) > width:
            last = last[:-1]
        lines[-1] = last + "."
    return lines


def _trophy(canvas: Canvas, x: int, y: int) -> None:
    gold = (255, 200, 60)
    canvas.rect(x, y, 5, 2, gold)
    canvas.rect(x + 1, y + 2, 3, 1, gold)
    canvas.px(x + 2, y + 3, gold)
    canvas.rect(x + 1, y + 4, 3, 1, gold)


def _clock_icon(canvas: Canvas, x: int, y: int, theme) -> None:
    canvas.circle(x + 2, y + 2, 2, theme.soft)
    canvas.px(x + 2, y + 1, theme.start)
    canvas.px(x + 3, y + 2, theme.start)


def _controller(canvas: Canvas, theme) -> None:
    body = (
        "..##########..",
        ".############.",
        "##.########.##",
        "#...######.#.#",
        "##.########.##",
        "##############",
        "#####....#####",
        ".###......###.",
    )
    x0, y0, size = (W - 14 * 3) // 2, 6, 3
    for gy, row in enumerate(body):
        for gx, cell in enumerate(row):
            if cell == "#":
                canvas.rect(x0 + gx * size, y0 + gy * size, size, size, mix(theme.start, theme.end, gx / 13))


SCENES = [CoverScene(), SessionScene()]
