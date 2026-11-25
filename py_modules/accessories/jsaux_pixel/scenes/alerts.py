"""Short-lived alerts (achievement unlocked) and the downloads scene.

An alert is one upload in and one upload back to the previous scene.
"""

import base64
import math

from .. import codec
from ..metrics import Stepper
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from ..render.text import plain_text
from .base import Scene, SceneContext, Segment

W, H = codec.WIDTH, codec.HEIGHT
ICON = 24
_GOLD = (255, 205, 70)
_TROPHY = (
    "#########",
    "#########",
    ".#######.",
    "..#####..",
    "...###...",
    "....#....",
    "...###...",
    "..#####..",
)


def _clean(text: str) -> str:
    return plain_text(text)


def _short(text: str, font: fonts.Font, width: int) -> str:
    text = _clean(text)
    while text and fonts.measure(text, font) > width:
        text = text[:-1]
    return text.rstrip()


class AlertScene(Scene):
    id = "alert"
    UPLOADS_PER_HOUR = 0

    def key(self, ctx: SceneContext):
        alert = ctx.options.get("alert") or {}
        return alert.get("kind"), alert.get("title"), bool(alert.get("icon"))

    def render(self, ctx: SceneContext) -> Segment:
        alert = ctx.options.get("alert") or {}
        frames = [self._frame(alert, i / 10, i) for i in range(10)]
        title = _clean(str(alert.get("title") or ""))
        width = fonts.measure(title, fonts.SMALL)
        if width <= W - 4:
            return Segment(frames, [8] * 9 + [400])
        delays = [8] * 10
        for offset in range(0, width + W, 2):
            frame = self._frame(alert, 1.0, 4)
            frame.text(W - offset, 42, title, fonts.SMALL, (255, 255, 255))
            frames.append(frame)
            delays.append(6)
        return Segment(frames, delays)

    def _frame(self, alert: dict, t: float, index: int) -> Canvas:
        canvas = Canvas()
        accent = _GOLD
        reveal = min(1.0, t * 1.6)
        for ray in range(12):
            angle = math.tau * (ray / 12 + t / 6)
            for r in range(16, 16 + round(10 * reveal)):
                canvas.px(round(32 + r * math.cos(angle)), round(18 + r * 0.8 * math.sin(angle)), scale(accent, 0.25))
        icon = self._icon(alert.get("icon"))
        x0, y0 = 32 - ICON // 2, 6
        if icon:
            for y in range(ICON):
                for x in range(ICON):
                    i = (y * ICON + x) * 3
                    if index >= 3:
                        canvas.px(x0 + x, y0 + y, (icon[i], icon[i + 1], icon[i + 2]))
            canvas.rect(x0 - 1, y0 - 1, ICON + 2, 1, accent)
            canvas.rect(x0 - 1, y0 + ICON, ICON + 2, 1, accent)
            canvas.rect(x0 - 1, y0, 1, ICON, accent)
            canvas.rect(x0 + ICON, y0, 1, ICON, accent)
        else:
            sprite = _TROPHY
            size = 2 if index >= 3 else 1
            sx = 32 - len(sprite[0]) * size // 2
            for gy, row in enumerate(sprite):
                for gx, cell in enumerate(row):
                    if cell == "#":
                        canvas.rect(sx + gx * size, 10 + gy * size, size, size, mix(accent, (255, 255, 255), 0.2 if gy < 2 else 0))
        canvas.rect(20, 35, 24, 1, scale(accent, 0.7))
        title = _clean(str(alert.get("title") or ""))
        if index >= 5 and fonts.measure(title, fonts.SMALL) <= W - 4:
            canvas.text((W - fonts.measure(title, fonts.SMALL)) // 2, 42, title, fonts.SMALL, (255, 255, 255))
        return canvas

    @staticmethod
    def _icon(encoded) -> bytes | None:
        try:
            raw = base64.b64decode(str(encoded or ""), validate=True)
        except ValueError:
            return None
        return raw if len(raw) == ICON * ICON * 3 else None


class DownloadScene(Scene):
    """Steam's current download: progress in 5 % steps and time left in minutes."""

    id = "game_download"
    UPLOADS_PER_HOUR = 24
    OPTIONS = ("theme",)

    def __init__(self):
        self._percent = Stepper(5, 1)
        self._minutes = Stepper(5, 2)

    def key(self, ctx: SceneContext):
        event = ctx.events.get("download") if isinstance(ctx.events, dict) else None
        if not isinstance(event, dict) or not event.get("total"):
            self._event = None
            return None, ctx.options.get("theme")
        self._event = event
        percent = 100 * min(1.0, float(event.get("done") or 0) / float(event["total"]))
        seconds = float(event.get("seconds") or 0)
        return (str(event.get("name")), self._percent(percent), self._minutes(seconds / 60) if seconds else None,
                bool(event.get("paused")), ctx.options.get("theme"))

    def render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        event = getattr(self, "_event", None)
        if event is None:
            canvas = Canvas()
            for gy, row in enumerate(("...##...", "...##...", "...##...", "########", ".######.", "..####..", "...##...")):
                for gx, cell in enumerate(row):
                    if cell == "#":
                        canvas.rect(20 + gx * 3, 8 + gy * 3, 3, 3, theme.dim if gy < 3 else scale(theme.start, 0.6))
            canvas.rect(14, 34, 36, 2, theme.dim)
            return Segment([canvas], [100])
        percent = self._percent.shown or 0
        frames = []
        for step in range(8):
            canvas = Canvas()
            name = _short(str(event.get("name") or "STEAM"), fonts.SMALL, W - 4)
            canvas.text((W - fonts.measure(name, fonts.SMALL)) // 2, 3, name, fonts.SMALL, theme.soft)
            text = f"{int(percent)}%"
            canvas.text((W - fonts.measure(text, fonts.big(14))) // 2, 14, text.rstrip("%"), fonts.big(14), (255, 255, 255))
            canvas.text((W + fonts.measure(text.rstrip("%"), fonts.big(14))) // 2 + 1, 14, "%", fonts.SMALL, theme.soft)
            filled = round(56 * percent / 100)
            for x in range(56):
                lit = x < filled
                shimmer = lit and not event.get("paused") and (x - step * 7) % 56 < 4
                colour = (255, 255, 255) if shimmer else mix(theme.start, theme.end, x / 55) if lit else theme.dim
                canvas.rect(4 + x, 34, 1, 4, colour)
            minutes = self._minutes.shown
            if event.get("paused"):
                canvas.rect(29, 42, 2, 7, theme.soft)
                canvas.rect(33, 42, 2, 7, theme.soft)
            elif minutes:
                left = f"{int(minutes)} MIN"
                canvas.text((W - fonts.measure(left, fonts.TINY)) // 2, 44, left, fonts.TINY, theme.soft)
            frames.append(canvas)
        return Segment(frames, [12] * len(frames))
