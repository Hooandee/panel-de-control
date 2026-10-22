"""Scenes about the game being played."""

import base64
import hashlib
from datetime import datetime, timedelta

from .. import codec
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .clocks import _centered, hour_segment

W, H = codec.WIDTH, codec.HEIGHT
_MARQUEE_CS = 9
_ART_BYTES = W * H * 3


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
    """The game's art, reduced by the UI to 64x54, with its name gliding along the bottom."""

    id = "game_cover"
    UPLOADS_PER_HOUR = 1

    def key(self, ctx: SceneContext):
        art = self._art(ctx)
        digest = hashlib.sha1(art).hexdigest() if art else None
        return (ctx.game or {}).get("appid"), digest

    def _art(self, ctx: SceneContext) -> bytes | None:
        event = ctx.events.get("game_art") if isinstance(ctx.events, dict) else None
        if not isinstance(event, dict):
            return None
        appid = (ctx.game or {}).get("appid")
        if appid is not None and str(event.get("appid")) != str(appid):
            return None
        try:
            raw = base64.b64decode(event.get("rgb") or "", validate=True)
        except (ValueError, TypeError):
            return None
        return raw if len(raw) == _ART_BYTES else None

    def render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        art = self._art(ctx)
        base = Canvas()
        if art:
            for y in range(H):
                for x in range(W):
                    i = (y * W + x) * 3
                    base.px(x, y, (art[i], art[i + 1], art[i + 2]))
        else:
            _controller(base, theme)
        title = _title(ctx.game) if ctx.game else "STEAM"
        width = fonts.measure(title, fonts.SMALL)
        if width <= W - 4:
            frame = base.copy()
            _band(frame, theme)
            _centered(frame, H - 8, title, fonts.SMALL, (255, 255, 255))
            return Segment([frame], [100])
        frames, travel = [], width + 16
        for offset in range(0, travel, 2):
            frame = base.copy()
            _band(frame, theme)
            frame.text(W - offset, H - 8, title, fonts.SMALL, (255, 255, 255))
            frames.append(frame)
        return Segment(frames, [_MARQUEE_CS] * len(frames))


def _band(canvas: Canvas, theme) -> None:
    for y in range(H - 10, H):
        for x in range(W):
            r, g, b = canvas.get(x, y)
            canvas.px(x, y, (r // 4, g // 4, b // 4))
    canvas.rect(0, H - 10, W, 1, scale(theme.start, 0.8))


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
