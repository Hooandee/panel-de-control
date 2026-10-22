"""A pixel creature that lives on the panel and reacts to what the Steam Machine is doing.

Each mood is one looping GIF; the mood changes only on events (a game starts or stops, the GPU
runs hot for a while), so the panel is written a handful of times per evening.
"""

import math
import random
from datetime import datetime

from .. import codec
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment

W, H = codec.WIDTH, codec.HEIGHT
STATES = ("sleep", "idle", "play", "hot", "party")
_HOT_ENTER, _HOT_EXIT = 82, 74
_PARTY_S = 60
_MOOD_DWELL_S = 450
_NIGHT = range(0, 7)

_BODY = (
    "......##########......",
    "....##############....",
    "...################...",
    "..##################..",
    ".####################.",
    ".####################.",
    "######################",
    "######################",
    "######################",
    "######################",
    "######################",
    ".####################.",
    ".####################.",
    "..##################..",
    "...################...",
    "....##############....",
)


class PetScene(Scene):
    id = "pet"
    UPLOADS_PER_HOUR = 8

    def __init__(self):
        self._mood: str | None = None
        self._since = 0.0
        self._hot = False

    def state(self, ctx: SceneContext) -> str:
        game = ctx.game
        if game:
            started = game.get("started_at")
            if isinstance(started, (int, float)) and 0 <= ctx.now - started < _PARTY_S:
                return "party"
            temp = ctx.metrics.get("gpu_temp")
            if isinstance(temp, (int, float)):
                if temp >= _HOT_ENTER:
                    self._hot = True
                elif temp <= _HOT_EXIT:
                    self._hot = False
            return "hot" if self._hot else "play"
        self._hot = False
        hour = datetime.fromtimestamp(ctx.now, ctx.tz).hour
        return "sleep" if hour in _NIGHT else "idle"

    def key(self, ctx: SceneContext):
        wanted = self.state(ctx)
        playing = {"play", "hot"}
        settled = wanted in playing and self._mood in playing
        if self._mood is None or (wanted != self._mood and (not settled or ctx.now - self._since >= _MOOD_DWELL_S)):
            self._mood, self._since = wanted, ctx.now
        return self._mood, ctx.options.get("theme")

    def render(self, ctx: SceneContext) -> Segment:
        if self._mood is None:
            self.key(ctx)
        return self.render_state(self._mood, ctx.options)

    def render_state(self, mood: str, options: dict) -> Segment:
        theme = theme_for(options)
        count, delay = {"sleep": (24, 12), "idle": (20, 8), "play": (16, 6), "hot": (16, 7), "party": (18, 6)}[mood]
        frames = [self._frame(mood, i / count, theme) for i in range(count)]
        return Segment(frames, [delay] * count)

    def _frame(self, mood: str, t: float, theme) -> Canvas:
        canvas = Canvas()
        rng = random.Random(9)
        bounce = {"sleep": 0.6, "idle": 1.5, "play": 3.0, "hot": 1.0, "party": 5.0}[mood]
        lift = abs(math.sin(math.tau * t * (2 if mood in ("play", "party") else 1))) * bounce
        x0, y0 = (W - 22) // 2, 24 - round(lift)
        body_colour = {"hot": (255, 90, 70), "sleep": scale(theme.start, 0.55)}.get(mood, theme.start)
        shadow = max(6, 11 - round(lift))
        for dx in range(-shadow, shadow + 1):
            canvas.px(W // 2 + dx, 47, scale(theme.dim, 1.6))
        for gy, row in enumerate(_BODY):
            for gx, cell in enumerate(row):
                if cell == "#":
                    shade = mix(body_colour, theme.end if mood != "hot" else (255, 170, 60), gy / len(_BODY))
                    if (gy, gx) in ((2, 6), (2, 7), (3, 5), (3, 6)):
                        shade = mix(shade, (255, 255, 255), 0.55)
                    canvas.px(x0 + gx, y0 + gy, shade)
        eye_y = y0 + 6
        for ex in (x0 + 6, x0 + 13):
            if mood == "sleep" or (mood == "idle" and 0.62 < t < 0.68):
                canvas.rect(ex, eye_y + 2, 3, 1, (30, 20, 40))
            else:
                canvas.rect(ex, eye_y, 3, 4, (255, 255, 255))
                look = 1 if mood == "play" and math.sin(math.tau * t) > 0 else 0
                canvas.rect(ex + look, eye_y + 1 + (1 if mood == "hot" else 0), 2, 2, (20, 16, 30))
        mouth_y = y0 + 12
        if mood in ("party", "play"):
            canvas.rect(x0 + 9, mouth_y, 4, 2, (60, 20, 50))
            canvas.rect(x0 + 10, mouth_y + 1, 2, 1, (255, 120, 150))
        elif mood == "hot":
            canvas.rect(x0 + 9, mouth_y + 1, 4, 1, (90, 30, 30))
        else:
            canvas.px(x0 + 10, mouth_y, (60, 20, 50))
            canvas.px(x0 + 11, mouth_y, (60, 20, 50))
        canvas.px(x0 + 4, eye_y + 5, scale((255, 120, 160), 0.7))
        canvas.px(x0 + 17, eye_y + 5, scale((255, 120, 160), 0.7))
        getattr(self, f"_extras_{mood}")(canvas, t, theme, rng, x0, y0)
        return canvas

    def _extras_sleep(self, canvas, t, theme, rng, x0, y0):
        for k in range(3):
            phase = (t + k / 3) % 1.0
            size = 3 + k % 2
            x, y = x0 + 20 + round(phase * 8), y0 - 1 - round(phase * 18)
            colour = scale(theme.soft, 1 - phase * 0.7)
            for i in range(size):
                canvas.px(x + i, y, colour)
                canvas.px(x + size - 1 - i, y + i, colour)
                canvas.px(x + i, y + size - 1, colour)

    def _extras_idle(self, canvas, t, theme, rng, x0, y0):
        for k in range(4):
            phase = (t + k / 4) % 1.0
            angle = math.tau * (k / 4 + t)
            canvas.px(W // 2 + round(math.cos(angle) * 22), 30 + round(math.sin(angle) * 14), scale(theme.spark, 0.4 + 0.6 * (1 - phase)))

    def _extras_play(self, canvas, t, theme, rng, x0, y0):
        pad_y = y0 + 15
        canvas.rect(x0 + 6, pad_y, 10, 4, (60, 60, 80))
        canvas.px(x0 + 8, pad_y + 1, theme.end)
        canvas.px(x0 + 13, pad_y + 1, theme.spark)
        canvas.px(x0 + 14, pad_y + 2, theme.start)
        for k in range(5):
            phase = (t * 2 + k / 5) % 1.0
            x = rng.randrange(4, W - 4)
            y = rng.randrange(4, 20)
            if phase < 0.5:
                canvas.px(x, y, scale(theme.spark, 1 - phase * 2))

    def _extras_hot(self, canvas, t, theme, rng, x0, y0):
        for k, side in enumerate((-3, 24, 3)):
            phase = (t + k / 3) % 1.0
            canvas.px(x0 + side, y0 + 2 + round(phase * 14), (120, 200, 255))
            canvas.px(x0 + side, y0 + 3 + round(phase * 14), (80, 160, 255))
        for k in range(3):
            phase = (t + k / 3) % 1.0
            wiggle = round(math.sin(math.tau * (phase * 2 + k)) * 1.5)
            canvas.px(x0 + 6 + k * 5 + wiggle, y0 - 2 - round(phase * 10), scale((220, 220, 230), 1 - phase))

    def _extras_party(self, canvas, t, theme, rng, x0, y0):
        palette = ((255, 90, 160), (90, 220, 255), (255, 220, 80), (140, 255, 140), (190, 120, 255))
        for k in range(26):
            x = rng.randrange(W)
            phase = (t + rng.random()) % 1.0
            y = round(phase * (H + 4)) - 4
            canvas.px(x + round(math.sin(math.tau * (phase * 2 + k)) * 1), y, palette[k % len(palette)])


SCENES = [PetScene()]
