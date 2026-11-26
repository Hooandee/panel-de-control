"""Live game readings drawn so they change rarely: values move in steps and animations carry the
"live" feel (a spinning fan, a beating heart) inside one looping GIF.
"""

import math
from datetime import datetime, timedelta

from .. import codec
from ..metrics import Stepper
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .clocks import _centered, _hm, hour_segment, short_date

W, H = codec.WIDTH, codec.HEIGHT
_DASH = "--"


def _value(metrics: dict, name: str) -> float | None:
    value = metrics.get(name)
    return value if isinstance(value, (int, float)) else None


def _fmt(value, suffix: str = "") -> str:
    return _DASH if value is None else f"{int(value)}{suffix}"


class LiveScene(Scene):
    METRIC = ""
    SETTLE = True
    OPTIONS = ("theme",)

    def render(self, ctx: SceneContext) -> Segment:
        segment = self._render(ctx)
        segment.kind, segment.metric = "live", self.METRIC
        return segment

    def _render(self, ctx: SceneContext) -> Segment:
        raise NotImplementedError


_FAN_BUCKETS = ((1, None), (700, 12), (1200, 7), (10_000_000, 4))


def _fan_speed(rpm: float | None) -> int | None:
    if rpm is None or rpm < _FAN_BUCKETS[0][0]:
        return None
    for limit, delay in _FAN_BUCKETS[1:]:
        if rpm < limit:
            return delay
    return _FAN_BUCKETS[-1][1]


class PowerScene(LiveScene):
    """Watts, temperatures and a fan whose spin speed follows the fan's RPM band."""

    id = "game_power"
    METRIC = "power"
    UPLOADS_PER_HOUR = 20

    def __init__(self):
        self._watts = Stepper(10, 4)
        self._gpu_temp = Stepper(3, 1)
        self._cpu_temp = Stepper(3, 1)
        self._rpm_band: int | None = None

    def key(self, ctx: SceneContext):
        m = ctx.metrics
        rpm = _value(m, "fan_rpm")
        band = _fan_speed(rpm)
        if band != self._rpm_band and (rpm is None or self._rpm_band is None or abs(_band_edge(rpm)) > 80):
            self._rpm_band = band
        return (self._watts(_value(m, "gpu_w")), self._gpu_temp(_value(m, "gpu_temp")),
                self._cpu_temp(_value(m, "cpu_temp")), self._rpm_band, ctx.options.get("theme"))

    def _render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        watts, gpu_temp, cpu_temp = self._watts.shown, self._gpu_temp.shown, self._cpu_temp.shown
        delay = self._rpm_band
        frames = [self._draw(step, theme, watts, gpu_temp, cpu_temp) for step in range(6 if delay else 1)]
        return Segment(frames, [delay or 100] * len(frames))

    def _draw(self, step, theme, watts, gpu_temp, cpu_temp) -> Canvas:
        canvas = Canvas()
        cx, cy = 13, 15
        canvas.circle(cx, cy, 11, theme.dim)
        for blade in range(4):
            angle = math.tau * (blade / 4 + step / 24)
            for r10 in range(15, 95, 4):
                r = r10 / 10
                spread = 0.42 * (r / 9.5)
                for da in (-spread, 0, spread):
                    canvas.px(round(cx + r * math.cos(angle + da)), round(cy + r * math.sin(angle + da)),
                              mix(theme.start, theme.end, r / 9.5))
        canvas.rect(cx - 1, cy - 1, 3, 3, theme.spark)
        text = _fmt(watts)
        canvas.text(W - 2 - fonts.measure(text, fonts.big(14)) - 7, 4, text, fonts.big(14), theme.end)
        canvas.text(W - 8, 13, "W", fonts.SMALL, theme.soft)
        canvas.text(28, 22, "GPU", fonts.TINY, theme.soft)
        canvas.rect(2, 31, W - 4, 1, theme.dim)
        _stat(canvas, 2, 36, "GPU", _fmt(gpu_temp, "°"), theme, gpu_temp, 95)
        _stat(canvas, 2, 45, "CPU", _fmt(cpu_temp, "°"), theme, cpu_temp, 95)
        return canvas


def _band_edge(rpm: float) -> float:
    return min((abs(rpm - limit) for limit, _ in _FAN_BUCKETS[1:-1]), default=1e9)


def _stat(canvas: Canvas, x: int, y: int, label: str, text: str, theme, value, ceiling) -> None:
    canvas.text(x, y, label, fonts.SMALL, theme.soft)
    canvas.text(W - 2 - fonts.measure(text, fonts.SMALL), y, text, fonts.SMALL, theme.start)
    left, width = x + 19, 22
    canvas.rect(left, y + 3, width, 1, theme.dim)
    if value is not None:
        filled = max(1, min(width, round(width * value / ceiling)))
        for i in range(filled):
            canvas.px(left + i, y + 3, mix(theme.end, theme.spark, i / width))


_HEART = (
    ".##...##.",
    "####.####",
    "#########",
    "#########",
    ".#######.",
    "..#####..",
    "...###...",
    "....#....",
)
_FPS_BEATS = ((1, 70), (30, 50), (60, 36), (90, 26), (10_000, 20))


class HeartScene(LiveScene):
    """A heart beating faster with higher frame rates; the number moves in steps of ten."""

    id = "game_heart"
    METRIC = "fps"
    UPLOADS_PER_HOUR = 20

    def __init__(self):
        self._fps = Stepper(10, 6)

    def key(self, ctx: SceneContext):
        return self._fps(_value(ctx.metrics, "fps")), ctx.options.get("theme")

    def _render(self, ctx: SceneContext) -> Segment:
        theme = theme_for({**ctx.options, "theme": ctx.options.get("theme", "sunset")})
        fps = self._fps.shown
        period = next(cs for limit, cs in _FPS_BEATS if fps is None or fps < limit) if fps else 90
        frames, delays = [], []
        for size, share in ((3, 0.18), (4, 0.14), (3, 0.16), (2, 0.52)):
            frames.append(self._draw(size, fps, theme))
            delays.append(max(3, round(period * share)))
        return Segment(frames, delays)

    def _draw(self, size: int, fps, theme) -> Canvas:
        canvas = Canvas()
        width, height = len(_HEART[0]) * size, len(_HEART) * size
        x0, y0 = (W - width) // 2, 2 + (32 - height) // 2
        for gy, row in enumerate(_HEART):
            for gx, cell in enumerate(row):
                if cell == "#":
                    colour = mix(theme.start, theme.end, gy / len(_HEART))
                    canvas.rect(x0 + gx * size, y0 + gy * size, size, size, colour)
        canvas.rect(x0 + size, y0 + size, size, size, scale(theme.spark, 1.0))
        text = _fmt(fps)
        _centered(canvas, 36, text, fonts.big(12), theme.spark)
        _centered(canvas, 49, "FPS", fonts.TINY, theme.soft)
        return canvas


class DashboardScene(LiveScene):
    """Date, clock and CPU/GPU/RAM/FPS bars, redrawn only when a bar moves."""

    id = "game_dashboard"
    OPTIONS = ("theme", "hour12")
    METRIC = "dashboard"
    UPLOADS_PER_HOUR = 30

    def __init__(self):
        self._steps = {name: Stepper(10, 4) for name in ("cpu_pct", "gpu_pct", "ram_pct")}
        self._fps = Stepper(10, 5)

    def key(self, ctx: SceneContext):
        t = datetime.fromtimestamp(ctx.now, ctx.tz)
        values = tuple(step(_value(ctx.metrics, name)) for name, step in self._steps.items())
        return t.strftime("%Y-%m-%d %H"), values, self._fps(_value(ctx.metrics, "fps")), ctx.options.get("theme")

    def _render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        values = {name: step.shown for name, step in self._steps.items()}
        fps = self._fps.shown
        start = datetime.fromtimestamp(ctx.now, ctx.tz)
        boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return hour_segment(start, boundary, lambda t: self._draw(t, ctx.options, theme, values, fps), lambda a, b: [])

    def _draw(self, t, options, theme, values, fps) -> Canvas:
        canvas = Canvas()
        canvas.text(1, 1, short_date(t, options), fonts.SMALL, theme.soft)
        hour, minute = _hm(t, options)
        clock = f"{hour:02d}:{minute:02d}"
        canvas.text(W - 1 - fonts.measure(clock, fonts.SMALL), 1, clock, fonts.SMALL, theme.start)
        rows = (("CPU", values["cpu_pct"], 100, "%"), ("GPU", values["gpu_pct"], 100, "%"),
                ("RAM", values["ram_pct"], 100, "%"), ("FPS", fps, 144, ""))
        for index, (label, value, ceiling, suffix) in enumerate(rows):
            y = 12 + index * 10
            canvas.text(1, y + 1, label, fonts.TINY, theme.soft)
            text = _fmt(value, suffix)
            colour = theme.spark if label == "FPS" else theme.start
            canvas.text(W - 1 - fonts.measure(text, fonts.TINY), y + 1, text, fonts.TINY, colour)
            bar_left, bar_width = 14, 34
            for i in range(bar_width):
                lit = value is not None and i < round(bar_width * min(value, ceiling) / ceiling)
                canvas.rect(bar_left + i, y + 1, 1, 5, mix(theme.start, theme.end, i / bar_width) if lit else theme.dim)
        return canvas


SCENES = [PowerScene(), HeartScene(), DashboardScene()]
