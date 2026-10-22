"""A pixel creature with a life of its own.

Every half hour a new, random "life script" is written to the panel as one GIF: mostly resting
(blinks, glances), and every few minutes an episode (eating, playing ball, napping, sneezing...).
Its mood follows the Steam Machine: asleep at night, playing with the controller during a game,
sweating when the GPU runs hot, partying when a game starts. Two writes per hour plus mood changes.
"""

import math
import random
from collections.abc import Callable
from datetime import datetime, timedelta

from .. import codec
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .fit import fits

W, H = codec.WIDTH, codec.HEIGHT
STATES = ("sleep", "idle", "play", "hot", "party")
_HOT_ENTER, _HOT_EXIT = 82, 74
_PARTY_S = 60
_MOOD_DWELL_S = 450
_NIGHT = range(0, 7)
_SCRIPT_MINUTES = 30
_EPISODE_CS = 6

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


class Pose:
    def __init__(self, dx=0, lift=0.0, squash=0, look=0, blink=False, happy=False, look_up=False, chomp=False, eyes_closed=False):
        self.dx, self.lift, self.squash, self.look = dx, lift, squash, look
        self.blink, self.happy, self.look_up, self.chomp, self.eyes_closed = blink, happy, look_up, chomp, eyes_closed


def draw_pet(canvas: Canvas, mood: str, theme, pose: Pose) -> tuple[int, int, int, int]:
    width, height = 22 + pose.squash, 16 - pose.squash
    x0 = (W - width) // 2 + pose.dx
    y0 = 40 - height - round(pose.lift)
    body = {"hot": (255, 90, 70), "sleep": scale(theme.start, 0.55)}.get(mood, theme.start)
    shadow = max(5, 11 - round(pose.lift / 2))
    for dx in range(-shadow, shadow + 1):
        canvas.px(W // 2 + pose.dx + dx, 41, scale(theme.dim, 1.6))
    for y in range(height):
        gy = min(len(_BODY) - 1, y * len(_BODY) // height)
        for x in range(width):
            gx = min(21, x * 22 // width)
            if _BODY[gy][gx] == "#":
                shade = mix(body, theme.end if mood != "hot" else (255, 170, 60), gy / len(_BODY))
                if (gy, gx) in ((2, 6), (2, 7), (3, 5), (3, 6)):
                    shade = mix(shade, (255, 255, 255), 0.55)
                canvas.px(x0 + x, y0 + y, shade)
    eye_y = y0 + round(height * 0.38)
    for ex in (x0 + round(width * 0.27), x0 + round(width * 0.6)):
        if pose.eyes_closed or pose.blink:
            canvas.rect(ex, eye_y + 2, 3, 1, (30, 20, 40))
        else:
            canvas.rect(ex, eye_y, 3, 4, (255, 255, 255))
            pupil_x = ex + (1 if pose.look > 0 else 0)
            pupil_y = eye_y + 1 + (1 if mood == "hot" else 0) - (1 if pose.look_up else 0)
            canvas.rect(pupil_x, pupil_y, 2, 2, (20, 16, 30))
    mouth_x, mouth_y = x0 + width // 2 - 2, y0 + round(height * 0.75)
    if pose.chomp:
        canvas.rect(mouth_x, mouth_y - 1, 4, 3, (60, 20, 50))
    elif pose.happy:
        canvas.rect(mouth_x, mouth_y, 4, 2, (60, 20, 50))
        canvas.rect(mouth_x + 1, mouth_y + 1, 2, 1, (255, 120, 150))
    elif mood == "hot":
        canvas.rect(mouth_x, mouth_y + 1, 4, 1, (90, 30, 30))
    else:
        canvas.rect(mouth_x + 1, mouth_y, 2, 1, (60, 20, 50))
    canvas.px(x0 + 3, eye_y + 5, scale((255, 120, 160), 0.7))
    canvas.px(x0 + width - 4, eye_y + 5, scale((255, 120, 160), 0.7))
    if mood == "play":
        pad_y = y0 + height - 3
        canvas.rect(x0 + width // 2 - 5, pad_y, 10, 4, (60, 60, 80))
        canvas.px(x0 + width // 2 - 3, pad_y + 1, theme.end)
        canvas.px(x0 + width // 2 + 2, pad_y + 1, theme.spark)
    if mood == "hot":
        canvas.px(x0 - 2, y0 + 4, (120, 200, 255))
        canvas.px(x0 + width + 1, y0 + 6, (120, 200, 255))
    return x0, y0, width, height


def _frame(mood: str, theme, pose: Pose, props: Callable[[Canvas, tuple], None] | None = None) -> Canvas:
    canvas = Canvas()
    box = draw_pet(canvas, mood, theme, pose)
    if props:
        props(canvas, box)
    return canvas


def _z(canvas: Canvas, x: int, y: int, size: int, colour) -> None:
    for i in range(size):
        canvas.px(x + i, y, colour)
        canvas.px(x + size - 1 - i, y + i, colour)
        canvas.px(x + i, y + size - 1, colour)


def _heart(canvas: Canvas, x: int, y: int, colour) -> None:
    for dx, dy in ((0, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (2, 2), (1, 3)):
        canvas.px(x + dx, y + dy, colour)


def _note(canvas: Canvas, x: int, y: int, colour) -> None:
    canvas.rect(x + 2, y, 1, 4, colour)
    canvas.rect(x, y + 3, 2, 2, colour)
    canvas.px(x + 3, y, colour)


def _ep_hop(mood, theme, n=24):
    out = []
    for i in range(n):
        phase = (i / n * 2) % 1.0
        lift = math.sin(math.pi * phase) * 9 if phase < 0.65 else 0.0
        squash = 3 if 0.65 <= phase < 0.75 else -1 if 0.1 < phase < 0.55 else 0
        out.append(_frame(mood, theme, Pose(lift=lift, squash=squash, happy=lift > 4, look_up=phase < 0.3)))
    return out


def _ep_dance(mood, theme, n=24):
    out = []
    for i in range(n):
        t = i / n
        wave = math.sin(math.tau * t * 2)

        def notes(canvas, box, t=t):
            for k in range(2):
                phase = (t * 2 + k / 2) % 1.0
                _note(canvas, box[0] - 6 + k * 34, 30 - round(phase * 22), scale(theme.spark, 1 - phase * 0.6))
        out.append(_frame(mood, theme, Pose(dx=round(wave * 6), lift=abs(wave) * 3, look=1 if wave > 0 else -1, happy=True), notes))
    return out


def _ep_wander(mood, theme, n=32):
    return [_frame(mood, theme, Pose(dx=round(math.sin(math.tau * i / n) * 18), lift=abs(math.sin(math.tau * i / n * 4)) * 2,
                                     look=1 if math.cos(math.tau * i / n) > 0 else -1)) for i in range(n)]


def _ep_stars(mood, theme, n=24):
    out = []
    for i in range(n):
        t = i / n

        def stars(canvas, box, t=t):
            for k in range(4):
                angle = math.tau * (t + k / 4)
                canvas.px(W // 2 + round(math.cos(angle) * 20), 30 + round(math.sin(angle) * 10), theme.spark)
        out.append(_frame(mood, theme, Pose(lift=abs(math.sin(math.tau * t)) * 2, look_up=True, happy=True), stars))
    return out


def _ep_apple(mood, theme):
    out = []
    for i in range(10):
        def apple(canvas, box, y=-4 + i * 2):
            canvas.circle(W // 2, y, 2, (230, 50, 60), filled=True)
            canvas.px(W // 2, y - 3, (90, 200, 90))
        out.append(_frame(mood, theme, Pose(look_up=True), apple))
    for bite in range(6):
        def eaten(canvas, box, bite=bite):
            size = 2 - bite // 2
            if size >= 0:
                canvas.circle(W // 2, box[1] + box[3] - 4, max(1, size), (230, 50, 60), filled=True)
        out.append(_frame(mood, theme, Pose(chomp=bite % 2 == 0, squash=1 if bite % 2 else 0), eaten))
    out += [_frame(mood, theme, Pose(happy=True, lift=lift)) for lift in (2, 4, 2, 0)]

    def hearts(canvas, box):
        _heart(canvas, box[0] + box[2] + 2, box[1] - 2, (255, 90, 150))
    out += [_frame(mood, theme, Pose(happy=True), hearts)] * 2
    return out


def _ep_ball(mood, theme):
    out = []
    path = [(62 - i * 3, 34 - round(abs(math.sin(i / 3)) * 14)) for i in range(10)]
    path += [(32 + i * 3, 10 - i) for i in range(1, 9)]
    for i, (bx, by) in enumerate(path):
        hit = 8 <= i <= 10

        def ball(canvas, box, bx=bx, by=by):
            canvas.circle(bx, by, 2, (255, 200, 60), filled=True)
            canvas.px(bx - 1, by - 1, (255, 255, 220))
        out.append(_frame(mood, theme, Pose(lift=4 if hit else 0, squash=-1 if hit else 0, look=1 if bx > W // 2 else -1,
                                             look_up=by < 20, happy=hit), ball))
    return out


def _ep_butterfly(mood, theme, n=28):
    out = []
    for i in range(n):
        t = i / n
        bx = W // 2 + round(math.sin(math.tau * t) * 24)
        by = 10 + round(math.sin(math.tau * t * 2) * 6)
        flap = i % 2

        def fly(canvas, box, bx=bx, by=by, flap=flap):
            wing = (255, 140, 220)
            canvas.px(bx, by, (40, 30, 30))
            canvas.px(bx - 1, by - flap, wing)
            canvas.px(bx + 1, by - flap, wing)
            canvas.px(bx - 2, by - 1 + flap, scale(wing, 0.8))
            canvas.px(bx + 2, by - 1 + flap, scale(wing, 0.8))
        out.append(_frame(mood, theme, Pose(look=1 if bx > W // 2 else -1, look_up=by < 14, happy=i > n // 2), fly))
    return out


def _ep_nap(mood, theme):
    out = []
    for i in range(16):
        def zs(canvas, box, i=i):
            phase = (i / 16 * 2) % 1.0
            _z(canvas, box[0] + box[2] + 1 + round(phase * 6), box[1] - 2 - round(phase * 14), 3, scale(theme.soft, 1 - phase * 0.6))
        out.append(_frame(mood, theme, Pose(squash=round(math.sin(math.tau * i / 8)), eyes_closed=True), zs))
    out += [_frame(mood, theme, Pose(squash=s, eyes_closed=s < 0)) for s in (-3, -3, -2, 0, 1, 0)]
    return out


def _ep_sneeze(mood, theme):
    out = [_frame(mood, theme, Pose(squash=s, eyes_closed=s > 1, look_up=True)) for s in (0, 1, 2, 3, 3)]
    for k in range(6):
        def burst(canvas, box, k=k):
            for j in range(6):
                angle = math.tau * j / 6
                canvas.px(W // 2 + round(math.cos(angle) * (4 + k * 3)), 30 + round(math.sin(angle) * (3 + k * 2)),
                          scale((220, 230, 255), 1 - k / 7))
        out.append(_frame(mood, theme, Pose(squash=-2 if k < 2 else 0, lift=3 if k < 2 else 0, chomp=k < 2), burst))
    return out


def _ep_peekaboo(mood, theme):
    out = [_frame(mood, theme, Pose(dx=-d, look=-1)) for d in range(0, 48, 6)]
    out += [Canvas()] * 3
    out += [_frame(mood, theme, Pose(dx=-38 + d, look=1, happy=d > 6)) for d in (0, 3, 6, 6)]
    out += [_frame(mood, theme, Pose(dx=-d, look=1, happy=True)) for d in range(30, -1, -6)]
    return out


def _ep_hearts(mood, theme, n=20):
    out = []
    for i in range(n):
        t = i / n

        def hearts(canvas, box, t=t):
            for k in range(3):
                phase = (t + k / 3) % 1.0
                _heart(canvas, W // 2 - 10 + k * 9, box[1] - 2 - round(phase * 16), scale((255, 90, 150), 1 - phase * 0.7))
        out.append(_frame(mood, theme, Pose(happy=True, squash=1 if i % 6 < 3 else 0), hearts))
    return out


def _ep_wave(mood, theme, n=16):
    out = []
    for i in range(n):
        def arm(canvas, box, i=i):
            x, y = box[0] + box[2], box[1] + 6
            tip = -2 if i % 4 < 2 else 1
            canvas.px(x, y, theme.start)
            canvas.px(x + 1, y - 1, theme.start)
            canvas.px(x + 2, y - 2 + tip, theme.start)
            if i % 4 < 2:
                canvas.px(x + 4, y - 5 - i % 3, theme.spark)
        sway = round(math.sin(math.tau * i / n) * 2)
        out.append(_frame(mood, theme, Pose(dx=sway, lift=1 if i % 4 < 2 else 0, happy=True, look=1), arm))
    return out


EPISODES: dict[str, Callable] = {
    "hop": _ep_hop, "dance": _ep_dance, "wander": _ep_wander, "stars": _ep_stars, "apple": _ep_apple,
    "ball": _ep_ball, "butterfly": _ep_butterfly, "nap": _ep_nap, "sneeze": _ep_sneeze, "peekaboo": _ep_peekaboo,
    "hearts": _ep_hearts, "wave": _ep_wave,
}
_MOOD_EPISODES = {
    "idle": ("hop", "dance", "wander", "stars", "apple", "ball", "butterfly", "nap", "sneeze", "peekaboo", "hearts", "wave"),
    "play": ("hop", "dance", "stars", "ball", "hearts", "wave", "wander"),
    "sleep": ("nap", "nap", "nap", "sneeze", "hearts"),
    "hot": ("sneeze", "wander", "nap", "hop"),
}


def episode_frames(name: str, mood: str, options: dict) -> list[tuple[Canvas, int]]:
    return [(canvas, _EPISODE_CS) for canvas in EPISODES[name](mood, theme_for(options))]


class PetScene(Scene):
    id = "pet"
    UPLOADS_PER_HOUR = 8
    OPTIONS = ("theme",)

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
        return self._mood, _slot(ctx), ctx.options.get("theme")

    def script(self, ctx: SceneContext) -> list[tuple[str, float]]:
        """(episode, seconds of rest before it) for the current half hour."""
        mood = self._mood or self.state(ctx)
        start, end = _window(ctx)
        rng = random.Random(f"{start.timestamp()}:{mood}")
        pool = _MOOD_EPISODES.get(mood, _MOOD_EPISODES["idle"])
        script, used, last = [], 0.0, None
        total = (end - start).total_seconds()
        while used < total:
            rest = rng.uniform(45, 120)
            name = rng.choice([p for p in pool if p != last] or pool)
            script.append((name, rest))
            used += rest + 4
            last = name
        return script

    def render(self, ctx: SceneContext) -> Segment:
        if self._mood is None:
            self.key(ctx)
        mood = self._mood
        if mood == "party":
            return self.render_state("party", ctx.options)
        theme = theme_for(ctx.options)
        _start, end = _window(ctx)
        now = datetime.fromtimestamp(ctx.now, ctx.tz)
        remaining_cs = round((end - now).total_seconds() * 100)
        script = self.script(ctx)
        while True:
            segment = self._life(mood, theme, script, remaining_cs, end.timestamp())
            if fits(segment) or len(script) <= 2:
                return segment
            script = script[::2]

    def _life(self, mood: str, theme, script, total_cs: int, until: float) -> Segment:
        rest = _frame(mood, theme, Pose(eyes_closed=mood == "sleep"))
        blink = _frame(mood, theme, Pose(blink=True))
        glance = _frame(mood, theme, Pose(look=-1, eyes_closed=mood == "sleep"))
        frames: list[Canvas] = [rest]
        delays: list[int] = [100]
        for name, rest_s in script:
            rest_cs = round(rest_s * 100)
            while rest_cs > 0:
                hold = min(rest_cs, 1500)
                frames.append(rest)
                delays.append(hold)
                rest_cs -= hold
                if rest_cs > 0 and mood != "sleep":
                    quick = len(frames) % 3 != 0
                    frames.append(blink if quick else glance)
                    delays.append(15 if quick else 120)
                    rest_cs -= delays[-1]
            for canvas in EPISODES[name](mood, theme):
                frames.append(canvas)
                delays.append(_EPISODE_CS)
        elapsed, kept_frames, kept_delays = 0, [], []
        for canvas, delay in zip(frames, delays):
            if elapsed + delay >= total_cs:
                kept_frames.append(canvas)
                kept_delays.append(max(1, total_cs - elapsed))
                elapsed = total_cs
                break
            kept_frames.append(canvas)
            kept_delays.append(delay)
            elapsed += delay
        if elapsed < total_cs:
            kept_frames.append(rest)
            kept_delays.append(total_cs - elapsed)
        return Segment(kept_frames, kept_delays, valid_until=until)

    def render_state(self, mood: str, options: dict, activity: str = "hop") -> Segment:
        """A short loop of one mood, used for the party burst and for gallery thumbnails."""
        theme = theme_for(options)
        if mood == "party":
            palette = ((255, 90, 160), (90, 220, 255), (255, 220, 80), (140, 255, 140), (190, 120, 255))
            rng = random.Random(9)
            confetti = [(rng.randrange(W), rng.random()) for _ in range(26)]
            frames = []
            for i in range(32):
                t = i / 32
                hop = abs(math.sin(math.tau * t * 2))

                def fall(canvas, box, t=t):
                    for k, (x, phase) in enumerate(confetti):
                        y = round(((t + phase) % 1.0) * (H + 4)) - 4
                        canvas.px(x, y, palette[k % len(palette)])
                frames.append(_frame("party", theme, Pose(lift=hop * 9, squash=2 if hop < 0.15 else -1, happy=True, look_up=True), fall))
            return Segment(frames, [5] * len(frames))
        name = {"hop": "hop", "dance": "dance", "wander": "wander", "spin": "stars"}.get(activity, "hop")
        frames = EPISODES[name](mood if mood in ("idle", "play", "hot", "sleep") else "idle", theme)
        return Segment(frames, [_EPISODE_CS] * len(frames))


ACTIVITIES = ("hop", "dance", "wander", "spin")


def activity_for(now: float) -> str:
    hour = int(now // 3600)
    return ACTIVITIES[random.Random(hour).randrange(len(ACTIVITIES))]


def _window(ctx: SceneContext) -> tuple[datetime, datetime]:
    now = datetime.fromtimestamp(ctx.now, ctx.tz)
    start = now.replace(minute=(now.minute // _SCRIPT_MINUTES) * _SCRIPT_MINUTES, second=0, microsecond=0)
    return start, start + timedelta(minutes=_SCRIPT_MINUTES)


def _slot(ctx: SceneContext) -> str:
    return _window(ctx)[0].isoformat()


SCENES = [PetScene()]
