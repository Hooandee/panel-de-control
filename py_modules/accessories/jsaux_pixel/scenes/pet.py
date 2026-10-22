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
    OPTIONS = ("theme",)
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
        self._activity = activity_for(ctx.now)
        return self._mood, self._activity, ctx.options.get("theme")

    def render(self, ctx: SceneContext) -> Segment:
        if self._mood is None:
            self.key(ctx)
        return self.render_state(self._mood, ctx.options, getattr(self, "_activity", ACTIVITIES[0]))

    def render_state(self, mood: str, options: dict, activity: str = "hop") -> Segment:
        theme = theme_for(options)
        count, delay = {"sleep": (32, 10), "idle": (48, 7), "play": (40, 5), "hot": (32, 7), "party": (32, 5)}[mood]
        frames = [self._frame(mood, i / count, theme, activity) for i in range(count)]
        return Segment(frames, [delay] * count)

    def _frame(self, mood: str, t: float, theme, activity: str = "hop") -> Canvas:
        canvas = Canvas()
        rng = random.Random(9)
        pose = _pose(mood, activity, t)
        width, height = 22 + pose.squash, 16 - pose.squash
        x0 = (W - width) // 2 + pose.dx
        y0 = 40 - height - round(pose.lift)
        body_colour = {"hot": (255, 90, 70), "sleep": scale(theme.start, 0.55)}.get(mood, theme.start)
        shadow = max(5, 11 - round(pose.lift / 2))
        for dx in range(-shadow, shadow + 1):
            canvas.px(W // 2 + pose.dx + dx, 41, scale(theme.dim, 1.6))
        for y in range(height):
            gy = min(len(_BODY) - 1, y * len(_BODY) // height)
            for x in range(width):
                gx = min(21, x * 22 // width)
                if _BODY[gy][gx] == "#":
                    shade = mix(body_colour, theme.end if mood != "hot" else (255, 170, 60), gy / len(_BODY))
                    if (gy, gx) in ((2, 6), (2, 7), (3, 5), (3, 6)):
                        shade = mix(shade, (255, 255, 255), 0.55)
                    canvas.px(x0 + x, y0 + y, shade)
        eye_y = y0 + round(height * 0.38)
        for ex in (x0 + round(width * 0.27), x0 + round(width * 0.6)):
            if mood == "sleep" or pose.blink:
                canvas.rect(ex, eye_y + 2, 3, 1, (30, 20, 40))
            else:
                canvas.rect(ex, eye_y, 3, 4, (255, 255, 255))
                canvas.rect(ex + (1 if pose.look > 0 else 0), eye_y + 1 + (1 if mood == "hot" else 0) - (1 if pose.look_up else 0),
                            2, 2, (20, 16, 30))
        mouth_x, mouth_y = x0 + width // 2 - 2, y0 + round(height * 0.75)
        if pose.happy or mood in ("party", "play"):
            canvas.rect(mouth_x, mouth_y, 4, 2, (60, 20, 50))
            canvas.rect(mouth_x + 1, mouth_y + 1, 2, 1, (255, 120, 150))
        elif mood == "hot":
            canvas.rect(mouth_x, mouth_y + 1, 4, 1, (90, 30, 30))
        else:
            canvas.rect(mouth_x + 1, mouth_y, 2, 1, (60, 20, 50))
        canvas.px(x0 + 3, eye_y + 5, scale((255, 120, 160), 0.7))
        canvas.px(x0 + width - 4, eye_y + 5, scale((255, 120, 160), 0.7))
        if activity == "spin" and mood in ("idle", "play"):
            for k in range(3):
                angle = math.tau * (t + k / 3)
                canvas.px(W // 2 + round(math.cos(angle) * 18), 30 + round(math.sin(angle) * 9), theme.spark)
                canvas.px(W // 2 + round(math.cos(angle) * 18) + 1, 30 + round(math.sin(angle) * 9), scale(theme.spark, 0.5))
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


ACTIVITIES = ("hop", "dance", "wander", "spin")


def activity_for(now: float) -> str:
    """A different pastime each hour, the same one all hour long (one write per hour at most)."""
    hour = int(now // 3600)
    return ACTIVITIES[random.Random(hour).randrange(len(ACTIVITIES))]


class _Pose:
    def __init__(self, dx=0, lift=0.0, squash=0, look=0, blink=False, happy=False, look_up=False):
        self.dx, self.lift, self.squash, self.look = dx, lift, squash, look
        self.blink, self.happy, self.look_up = blink, happy, look_up


def _pose(mood: str, activity: str, t: float) -> _Pose:
    wave = math.sin(math.tau * t)
    blink = 0.86 < t < 0.9 or 0.36 < t < 0.39
    if mood == "sleep":
        return _Pose(squash=round(math.sin(math.tau * t) * 1), blink=True)
    if mood == "hot":
        return _Pose(dx=round(math.sin(math.tau * t * 2) * 1), squash=1, look=0, blink=blink)
    if mood == "party":
        hop = abs(math.sin(math.tau * t * 2))
        return _Pose(lift=hop * 9, squash=2 if hop < 0.15 else -1, happy=True, look_up=True)
    speed = 2 if mood == "play" else 1
    if activity == "dance":
        hop = abs(math.sin(math.tau * t * 2 * speed))
        return _Pose(dx=round(wave * 5), lift=hop * 3, squash=2 if hop < 0.2 else 0, look=1 if wave > 0 else -1,
                     happy=True, blink=blink)
    if activity == "wander":
        step = abs(math.sin(math.tau * t * 4))
        return _Pose(dx=round(wave * 13), lift=step * 2, look=1 if math.cos(math.tau * t) > 0 else -1, blink=blink)
    if activity == "spin":
        return _Pose(lift=abs(wave) * 2, look=1 if wave > 0 else -1, happy=True, look_up=True, blink=blink)
    phase = (t * 2 * speed) % 1.0
    lift = math.sin(math.pi * phase) * 8 if phase < 0.6 else 0.0
    squash = 3 if 0.6 <= phase < 0.7 else -1 if 0.1 < phase < 0.5 else 0
    return _Pose(lift=lift, squash=squash, look_up=phase < 0.3, blink=blink, happy=lift > 5)


SCENES = [PetScene()]
