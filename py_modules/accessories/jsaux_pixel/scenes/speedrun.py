"""A speedrun timer that starts with the game.

The panel loops whole GIFs, so every second of the next few minutes is rendered in advance and
written once: a frame per second, each one only the digits that changed. A new window is
written when the previous one runs out, which also re-syncs the timer with the real clock.
"""

from .. import codec
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .clocks import _centered
from ..render.text import big_fitting, fit
from .fit import fits
from .game import _title
from .words import Words, words

W, H = codec.WIDTH, codec.HEIGHT
_WINDOW_S = 600
_MIN_WINDOW_S = 300


def _run(ctx: SceneContext) -> tuple[float | None, float | None]:
    """(origin, paused_at): a reset or pause from the UI, else the game's start."""
    run = ctx.events.get("speedrun") if isinstance(ctx.events, dict) else None
    if isinstance(run, dict) and isinstance(run.get("origin"), (int, float)):
        paused = run.get("paused_at")
        return float(run["origin"]), float(paused) if isinstance(paused, (int, float)) else None
    started = (ctx.game or {}).get("started_at")
    return (float(started), None) if isinstance(started, (int, float)) else (None, None)


def elapsed(ctx: SceneContext) -> int:
    origin, paused = _run(ctx)
    if origin is None:
        return 0
    return max(0, int((paused if paused is not None else ctx.now) - origin))


def clock_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


class SpeedrunScene(Scene):
    id = "speedrun"
    UPLOADS_PER_HOUR = 12
    OPTIONS = ("run", "theme")

    def key(self, ctx: SceneContext):
        origin, paused = _run(ctx)
        if origin is None or paused is not None or not ctx.game:
            return (ctx.game or {}).get("appid"), origin, paused, ctx.options.get("theme")
        window = int((ctx.now - origin) // _WINDOW_S)
        return (ctx.game or {}).get("appid"), origin, window, ctx.options.get("theme")

    def render(self, ctx: SceneContext) -> Segment:
        theme = theme_for(ctx.options)
        origin, paused = _run(ctx)
        title = _title(ctx.game) if ctx.game else "SPEEDRUN"
        if origin is None or not ctx.game:
            return Segment([_face(theme, words(ctx.options), title, "0:00", 0.0, waiting=True)], [100])
        if paused is not None:
            seconds = elapsed(ctx)
            still = _face(theme, words(ctx.options), title, clock_text(seconds), (seconds % 60) / 60, paused=True)
            return Segment([still], [100])
        now_s = ctx.now - origin
        span = _WINDOW_S
        while True:
            end_s = (int(now_s // _WINDOW_S) * _WINDOW_S) + _WINDOW_S if span == _WINDOW_S else now_s + span
            segment = self._window(theme, words(ctx.options), title, now_s, end_s, origin)
            if fits(segment) or span <= _MIN_WINDOW_S:
                return segment
            span = _MIN_WINDOW_S

    def _window(self, theme, said: Words, title: str, now_s: float, end_s: float, origin: float) -> Segment:
        frames: list[Canvas] = []
        delays: list[int] = []
        second = int(now_s)
        shown_from = now_s
        while second < end_s:
            following = min(second + 1, end_s)
            frames.append(_face(theme, said, title, clock_text(second), (second % 60) / 60))
            delays.append(max(1, round((following - shown_from) * 100)))
            shown_from = following
            second += 1
        total = round((end_s - now_s) * 100)
        delays[-1] += total - sum(delays)
        return Segment(frames, delays, valid_until=origin + end_s)


def _face(theme, said: Words, title: str, text: str, minute_progress: float, paused: bool = False, waiting: bool = False) -> Canvas:
    canvas = Canvas()
    _centered(canvas, 3, fit(title, fonts.TINY, W - 4), fonts.TINY, theme.soft)
    font = big_fitting(text, (16, 12, 10), W - 2)
    y = 14 + (16 - font.height) // 2
    colour = theme.dim if waiting else scale(theme.start, 0.6) if paused else theme.start
    _centered(canvas, y, text, font, colour)
    label = said.paused if paused else said.ready if waiting else "RUN"
    _centered(canvas, 37, label, fonts.TINY, theme.end if not paused else theme.soft)
    filled = round(56 * minute_progress)
    for i in range(56):
        canvas.px(4 + i, 47, mix(theme.start, theme.end, i / 55) if i < filled else theme.dim)
    return canvas
