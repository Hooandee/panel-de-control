"""Clocks precomputed one hour at a time: one GIF frame per minute, swapped at the hour.

Write cost: one upload per hour. Frames after the first only carry the digits that changed, so a
full hour stays a few kilobytes.
"""

import math
from collections.abc import Callable
from datetime import datetime, timedelta

from .. import codec
from ..render import fonts
from ..render.canvas import BLACK, Canvas
from ..render.palettes import Theme, mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .fit import fits
from .words import words



def short_date(t: datetime, options: dict | None) -> str:
    return f"{words(options).days[t.weekday()]} {t.day:02d}"


def long_date(t: datetime, options: dict | None) -> str:
    said = words(options)
    return f"{said.days[t.weekday()]} {t.day:02d} {said.months[t.month - 1]}"

_TRANSITION_CS = 6


def _hm(t: datetime, options: dict) -> tuple[int, int]:
    hour = t.hour
    if options.get("hour12"):
        hour = hour % 12 or 12
    return hour, t.minute


def _centered(canvas: Canvas, y: int, text: str, font: fonts.Font, colour) -> int:
    x = (codec.WIDTH - fonts.measure(text, font)) // 2
    canvas.text(x, y, text, font, colour)
    return x


def _gradient_text(canvas: Canvas, y: int, text: str, font: fonts.Font, theme: Theme) -> None:
    layer = Canvas()
    x = _centered(layer, y, text, font, (255, 255, 255))
    width = fonts.measure(text, font)
    for py in range(codec.HEIGHT):
        for px in range(codec.WIDTH):
            if layer.get(px, py) == (255, 255, 255):
                canvas.px(px, py, mix(theme.start, theme.end, (px - x) / max(1, width - 1)))


class HourClock(Scene):
    UPLOADS_PER_HOUR = 1
    OPTIONS = ("theme", "hour12")

    def key(self, ctx: SceneContext):
        t = datetime.fromtimestamp(ctx.now, ctx.tz)
        return t.strftime("%Y-%m-%d %H"), ctx.tz.utcoffset(t) if ctx.tz else None

    def draw(self, t: datetime, options: dict) -> Canvas:
        raise NotImplementedError

    def transition(self, before: datetime, after: datetime, options: dict) -> list[Canvas]:
        return []

    def render(self, ctx: SceneContext) -> Segment:
        start = datetime.fromtimestamp(ctx.now, ctx.tz)
        boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return hour_segment(start, boundary, lambda t: self.draw(t, ctx.options),
                            lambda a, b: self.transition(a, b, ctx.options))


def hour_segment(start: datetime, boundary: datetime, draw: Callable[[datetime], Canvas],
                 transition: Callable[[datetime, datetime], list[Canvas]]) -> Segment:
    def offset(t: datetime) -> int:
        return round((t - start).total_seconds() * 100)

    end = boundary
    while True:
        frames: list[Canvas] = []
        delays: list[int] = []
        minute = start.replace(second=0, microsecond=0)
        previous = None
        while minute < end:
            following = min(minute + timedelta(minutes=1), end)
            shown_from = max(minute, start)
            budget = offset(following) - offset(shown_from)
            steps = transition(previous, minute) if previous is not None else []
            for step in steps:
                frames.append(step)
                delays.append(_TRANSITION_CS)
                budget -= _TRANSITION_CS
            frames.append(draw(minute))
            delays.append(max(1, budget))
            previous = minute
            minute = following
        segment = Segment(frames, delays, valid_until=end.timestamp())
        if fits(segment) or end - start <= timedelta(minutes=5):
            return segment
        end = start + (end - start) / 2


class DigitalClock(HourClock):
    id = "clock_digital"

    def draw(self, t: datetime, options: dict) -> Canvas:
        theme = theme_for(options)
        canvas = Canvas()
        _centered(canvas, 3, long_date(t, options), fonts.SMALL, theme.soft)
        hour, minute = _hm(t, options)
        _gradient_text(canvas, 15, f"{hour:02d}:{minute:02d}", fonts.big(19), theme)
        left = (codec.WIDTH - 60) // 2
        for m in range(60):
            lit = m <= minute
            colour = mix(theme.start, theme.end, m / 59) if lit else theme.dim
            tall = 2 if m % 15 == 0 else 1
            canvas.rect(left + m, 46 - (tall - 1), 1, tall + 1, colour if lit else theme.dim)
        canvas.px(left + minute, 44, theme.spark)
        return canvas


class AnalogClock(HourClock):
    id = "clock_analog"

    def draw(self, t: datetime, options: dict) -> Canvas:
        theme = theme_for(options)
        canvas = Canvas()
        cx, cy, radius = 31.5, 26.5, 25
        for step in range(360):
            angle = math.tau * step / 360
            canvas.px(round(cx + radius * math.cos(angle) - 0.5), round(cy + radius * math.sin(angle) - 0.5), theme.dim)
        for hour in range(12):
            angle = math.tau * hour / 12 - math.pi / 2
            colour = mix(theme.start, theme.end, hour / 11)
            for r in ((radius - 2, radius - 4) if hour % 3 == 0 else (radius - 2,)):
                canvas.px(round(cx + r * math.cos(angle) - 0.5), round(cy + r * math.sin(angle) - 0.5), colour)
        dot = math.tau * t.minute / 60 - math.pi / 2
        canvas.px(round(cx + radius * math.cos(dot) - 0.5), round(cy + radius * math.sin(dot) - 0.5), theme.spark)
        minute_angle = math.tau * t.minute / 60 - math.pi / 2
        hour_angle = math.tau * ((t.hour % 12) + t.minute / 60) / 12 - math.pi / 2
        _hand(canvas, cx, cy, hour_angle, 12, theme.start)
        _hand(canvas, cx, cy, minute_angle, 19, theme.end)
        canvas.rect(30, 25, 3, 3, theme.spark)
        canvas.px(30, 25, BLACK)
        canvas.px(32, 25, BLACK)
        canvas.px(30, 27, BLACK)
        canvas.px(32, 27, BLACK)
        return canvas


def _hand(canvas: Canvas, cx: float, cy: float, angle: float, length: int, colour) -> None:
    for r10 in range(0, length * 10 + 1, 3):
        r = r10 / 10
        x, y = cx + r * math.cos(angle) - 0.5, cy + r * math.sin(angle) - 0.5
        canvas.px(round(x), round(y), colour)
        if r < length - 2:
            canvas.px(round(x + 0.5), round(y), colour)
            canvas.px(round(x), round(y + 0.5), colour)


_BLOCK = 4
_TETRIS_COLOURS = ((80, 220, 255), (255, 210, 70), (190, 110, 255), (110, 230, 120), (255, 110, 110), (255, 160, 70))


def _block(canvas: Canvas, x: int, y: int, colour) -> None:
    canvas.rect(x, y, _BLOCK - 1, _BLOCK - 1, colour)
    canvas.px(x, y, scale(colour, 1.3))


class TetrisClock(HourClock):
    """Digits built from falling blocks; only the digits that change drop in each minute."""

    id = "clock_tetris"
    _FALL_FRAMES = 7

    def _layout(self, t: datetime, options: dict) -> list[tuple[str, int]]:
        hour, minute = _hm(t, options)
        text = f"{hour:02d}{minute:02d}"
        width = 3 * _BLOCK
        gap = 2
        total = 4 * width + 3 * gap + 4
        left = (codec.WIDTH - total) // 2
        xs = [left, left + width + gap, left + 2 * (width + gap) + 4, left + 3 * (width + gap) + 4]
        return list(zip(text, xs))

    def _draw(self, t: datetime, options: dict, falling: dict[int, int] | None = None) -> Canvas:
        canvas = Canvas()
        theme = theme_for(options)
        top = 10
        for index, (digit, x) in enumerate(self._layout(t, options)):
            colour = _TETRIS_COLOURS[(int(digit) + index) % len(_TETRIS_COLOURS)]
            rows = fonts.TINY.glyph(digit)
            drop = (falling or {}).get(index, 0)
            for gy, row in enumerate(rows):
                for gx, cell in enumerate(row):
                    if cell == "#":
                        y = top + gy * _BLOCK - drop * (len(rows) - gy)
                        if y > -_BLOCK:
                            _block(canvas, x + gx * _BLOCK, y, colour)
        colon_x = self._layout(t, options)[1][1] + 3 * _BLOCK + 2
        canvas.rect(colon_x, top + 5, 2, 2, theme.soft)
        canvas.rect(colon_x, top + 13, 2, 2, theme.soft)
        for x in range(4, codec.WIDTH - 4):
            canvas.px(x, 38, theme.dim)
        _centered(canvas, 43, short_date(t, options), fonts.TINY, theme.soft)
        return canvas

    def draw(self, t: datetime, options: dict) -> Canvas:
        return self._draw(t, options)

    def transition(self, before: datetime, after: datetime, options: dict) -> list[Canvas]:
        old = [d for d, _ in self._layout(before, options)]
        new = [d for d, _ in self._layout(after, options)]
        changed = [i for i in range(4) if old[i] != new[i]]
        frames = []
        for step in range(self._FALL_FRAMES, 0, -1):
            frames.append(self._draw(after, options, {i: step for i in changed}))
        return frames


class HourglassClock(HourClock):
    """Sand runs out over the hour: the top bulb empties one grain row per few minutes."""

    id = "clock_hourglass"

    def draw(self, t: datetime, options: dict) -> Canvas:
        theme = theme_for(options)
        canvas = Canvas()
        cx, top, half = 18, 4, 21
        glass = theme.soft
        for dy in range(half):
            w = max(1, round(12 * (1 - dy / half)))
            canvas.px(cx - w - 1, top + dy, glass)
            canvas.px(cx + w + 1, top + dy, glass)
            canvas.px(cx - w - 1, top + 2 * half - dy, glass)
            canvas.px(cx + w + 1, top + 2 * half - dy, glass)
        canvas.rect(cx - 14, top - 1, 30, 1, glass)
        canvas.rect(cx - 14, top + 2 * half + 1, 30, 1, glass)
        used = t.minute / 60
        cells_top = [(x, top + dy) for dy in range(half) for x in range(cx - round(12 * (1 - dy / half)), cx + round(12 * (1 - dy / half)) + 1)]
        cells_bottom = [(x, top + 2 * half - dy) for dy in range(half) for x in range(cx - round(12 * (1 - dy / half)), cx + round(12 * (1 - dy / half)) + 1)]
        keep_top = round(len(cells_top) * (1 - used))
        for i, (x, y) in enumerate(sorted(cells_top, key=lambda c: -c[1])):
            if i < keep_top:
                canvas.px(x, y, mix(theme.start, theme.end, (y - top) / half))
        fill_bottom = round(len(cells_bottom) * used)
        for i, (x, y) in enumerate(sorted(cells_bottom, key=lambda c: -c[1])):
            if i < fill_bottom:
                canvas.px(x, y, mix(theme.end, theme.start, (top + 2 * half - y) / half))
        if 0 < t.minute:
            canvas.rect(cx, top + half - 1, 1, half // 2, theme.spark)
        hour, minute = _hm(t, options)
        canvas.text(38, 12, f"{hour:02d}", fonts.big(12), theme.start)
        canvas.text(38, 28, f"{minute:02d}", fonts.big(12), theme.end)
        return canvas


SCENES = [DigitalClock(), AnalogClock(), TetrisClock(), HourglassClock()]
