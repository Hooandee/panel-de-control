"""A pixel creature with a life of its own.

Its mind (`pet_mind`) keeps needs, personality and memories, and plans what it does. This scene
turns that plan into ten minutes of life written to the panel as one GIF: short rests with
blinks and glances between actions chosen by the brain. Outside events change it at once: a game
starting (it reacts to the genre), the fan roaring (it gets blown away), heat (it sweats), and
care from the UI (it eats, plays, purrs). Rests and moods cost nothing extra: they are already
rehearsed inside the window.
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
from .pet_mind import Mind, genre_for

W, H = codec.WIDTH, codec.HEIGHT
_HOT_ENTER, _HOT_EXIT = 82, 74
_WIND_ENTER, _WIND_EXIT = 0.85, 0.65
_REACTION_S = 90
_DWELL_S = 300
_SCRIPT_MINUTES = 10
_EPISODE_CS = 6
_FRIGHT = 0.35

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
_INK = (30, 20, 40)
_MOUTH = (60, 20, 50)
_SWEAT = (120, 200, 255)


class Pose:
    def __init__(self, dx=0, lift=0.0, squash=0, look=0, blink=False, happy=False, look_up=False, chomp=False,
                 eyes_closed=False, face=None, band=False, arms=None, shake=0):
        self.dx, self.lift, self.squash, self.look = dx + shake, lift, squash, look
        self.blink, self.happy, self.look_up, self.chomp, self.eyes_closed = blink, happy, look_up, chomp, eyes_closed
        self.face, self.band, self.arms = face, band, arms


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
    if pose.band:
        canvas.rect(x0 + 2, y0 + 2, width - 4, 2, (230, 40, 60))
        canvas.px(x0 + width - 1, y0 + 3, (230, 40, 60))
        canvas.px(x0 + width, y0 + 4, (230, 40, 60))
    _eyes(canvas, mood, pose, x0, y0, width, height)
    _mouth(canvas, mood, pose, x0, y0, width, height)
    eye_y = y0 + round(height * 0.38)
    canvas.px(x0 + 3, eye_y + 5, scale((255, 120, 160), 0.7))
    canvas.px(x0 + width - 4, eye_y + 5, scale((255, 120, 160), 0.7))
    if pose.arms == "up":
        for side, x in ((-1, x0 - 1), (1, x0 + width)):
            canvas.px(x, y0 + 6, theme.start)
            canvas.px(x + side, y0 + 5, theme.start)
            canvas.px(x + side, y0 + 4, theme.start)
    elif pose.arms == "out":
        canvas.rect(x0 - 3, y0 + 8, 3, 1, theme.start)
        canvas.rect(x0 + width, y0 + 8, 3, 1, theme.start)
    if mood == "play" and pose.arms is None:
        pad_y = y0 + height - 3
        canvas.rect(x0 + width // 2 - 5, pad_y, 10, 4, (60, 60, 80))
        canvas.px(x0 + width // 2 - 3, pad_y + 1, theme.end)
        canvas.px(x0 + width // 2 + 2, pad_y + 1, theme.spark)
    if mood == "hot":
        canvas.px(x0 - 2, y0 + 4, _SWEAT)
        canvas.px(x0 + width + 1, y0 + 6, _SWEAT)
    return x0, y0, width, height


def _eyes(canvas: Canvas, mood: str, pose: Pose, x0: int, y0: int, width: int, height: int) -> None:
    eye_y = y0 + round(height * 0.38)
    for index, ex in enumerate((x0 + round(width * 0.27), x0 + round(width * 0.6))):
        face = pose.face
        if pose.eyes_closed or pose.blink:
            canvas.rect(ex, eye_y + 2, 3, 1, _INK)
            if pose.happy and pose.eyes_closed:
                canvas.px(ex + 1, eye_y + 1, _INK)
            continue
        if face == "love":
            for dx, dy in ((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)):
                canvas.px(ex + dx, eye_y + 1 + dy, (255, 80, 140))
            continue
        if face == "dizzy":
            for d in range(3):
                canvas.px(ex + d, eye_y + d, _INK)
                canvas.px(ex + 2 - d, eye_y + d, _INK)
            continue
        if face == "sleepy":
            canvas.rect(ex, eye_y + 2, 3, 2, (255, 255, 255))
            canvas.rect(ex, eye_y + 1, 3, 1, _INK)
            canvas.px(ex + 1, eye_y + 3, _INK)
            continue
        if face == "focused":
            canvas.rect(ex, eye_y + 1, 3, 2, (255, 255, 255))
            canvas.rect(ex + (1 if pose.look >= 0 else 0), eye_y + 1, 2, 2, (20, 16, 30))
            canvas.rect(ex - (1 if index == 0 else 0), eye_y - 1, 4, 1, _INK)
            continue
        canvas.rect(ex, eye_y, 3, 4, (255, 255, 255))
        if face == "scared":
            canvas.px(ex + 1, eye_y + 1, (20, 16, 30))
            continue
        pupil_x = ex + (1 if pose.look > 0 else 0)
        pupil_y = eye_y + 1 + (1 if mood == "hot" or face == "sad" else 0) - (1 if pose.look_up else 0)
        canvas.rect(pupil_x, pupil_y, 2, 2, (20, 16, 30))
        if face == "sad":
            brow = eye_y - 1
            canvas.px(ex + (2 if index == 0 else 0), brow - 1, _INK)
            canvas.px(ex + 1, brow, _INK)


def _mouth(canvas: Canvas, mood: str, pose: Pose, x0: int, y0: int, width: int, height: int) -> None:
    mouth_x, mouth_y = x0 + width // 2 - 2, y0 + round(height * 0.75)
    if pose.chomp:
        canvas.rect(mouth_x, mouth_y - 1, 4, 3, _MOUTH)
    elif pose.happy:
        canvas.rect(mouth_x, mouth_y, 4, 2, _MOUTH)
        canvas.rect(mouth_x + 1, mouth_y + 1, 2, 1, (255, 120, 150))
    elif pose.face == "scared":
        for i in range(4):
            canvas.px(mouth_x + i, mouth_y + (i % 2), _MOUTH)
    elif pose.face == "sad":
        canvas.rect(mouth_x + 1, mouth_y, 2, 1, _MOUTH)
        canvas.px(mouth_x, mouth_y + 1, _MOUTH)
        canvas.px(mouth_x + 3, mouth_y + 1, _MOUTH)
    elif mood == "hot" or pose.face == "focused":
        canvas.rect(mouth_x, mouth_y + 1, 4, 1, (90, 30, 30))
    else:
        canvas.rect(mouth_x + 1, mouth_y, 2, 1, _MOUTH)


def _frame(mood: str, theme, pose: Pose, props: Callable[[Canvas, tuple], None] | None = None,
           behind: Callable[[Canvas], None] | None = None) -> Canvas:
    canvas = Canvas()
    if behind:
        behind(canvas)
    box = draw_pet(canvas, mood, theme, pose)
    if props:
        props(canvas, box)
    return canvas


def _bubble(canvas: Canvas, x: int, y: int, w: int = 11, h: int = 9) -> None:
    edge, fill = (200, 200, 220), (40, 40, 60)
    canvas.rect(x + 1, y, w - 2, 1, edge)
    canvas.rect(x + 1, y + h - 1, w - 2, 1, edge)
    canvas.rect(x, y + 1, 1, h - 2, edge)
    canvas.rect(x + w - 1, y + 1, 1, h - 2, edge)
    canvas.rect(x + 1, y + 1, w - 2, h - 2, fill)
    canvas.px(x - 1, y + h, edge)
    canvas.px(x - 3, y + h + 2, edge)


def _apple(canvas: Canvas, x: int, y: int, r: int = 2) -> None:
    canvas.circle(x, y, r, (230, 50, 60), filled=True)
    canvas.px(x, y - r - 1, (90, 200, 90))
    canvas.px(x - 1, y - 1, (255, 160, 160))


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




# Needs ----------------------------------------------------------------------------------------

def _ep_snack(mood, theme):
    out = []
    for i in range(8):
        def rolling(canvas, box, x=-4 + i * 4):
            _apple(canvas, x, 38)
        out.append(_frame(mood, theme, Pose(look=-1, look_up=False, dx=-i // 2), rolling))
    for bite in range(6):
        def eaten(canvas, box, bite=bite):
            if bite < 5:
                _apple(canvas, box[0] - 2, 36, max(1, 2 - bite // 2))
        out.append(_frame(mood, theme, Pose(dx=-4, chomp=bite % 2 == 0, look=-1), eaten))
    out += [_frame(mood, theme, Pose(dx=-4 + k, happy=True, lift=(2, 3, 1, 0)[k])) for k in range(4)]
    return out


def _ep_hungry(mood, theme):
    out = []
    for i in range(18):
        def thought(canvas, box, i=i):
            if i >= 4:
                _bubble(canvas, box[0] + box[2] + 2, max(1, box[1] - 12))
                _apple(canvas, box[0] + box[2] + 7, max(1, box[1] - 12) + 4)
            if i % 6 < 3:
                canvas.px(box[0] - 2, box[1] + 10 + i % 3, theme.soft)
                canvas.px(box[0] + box[2] + 1, box[1] + 11 - i % 3, theme.soft)
        out.append(_frame(mood, theme, Pose(squash=1 if i % 6 < 3 else 0, face="sad", look_up=i >= 4), thought))
    return out


def _ep_yawn(mood, theme):
    out = [_frame(mood, theme, Pose(squash=-s, chomp=s > 0, eyes_closed=s > 1)) for s in (0, 1, 2, 3, 3, 3, 2, 1)]
    out += [_frame(mood, theme, Pose(face="sleepy", squash=1)) for _ in range(4)]
    out += [_frame(mood, theme, Pose(blink=True)), _frame(mood, theme, Pose(face="sleepy"))]
    return out


def _ep_call(mood, theme):
    out = []
    for i in range(20):
        def ask(canvas, box, i=i):
            x = box[0] + box[2] // 2
            if i < 10 and i % 4 < 3:
                canvas.rect(x, box[1] - 9, 1, 5, (255, 220, 80))
                canvas.px(x, box[1] - 3, (255, 220, 80))
            if i >= 10:
                _bubble(canvas, box[0] + box[2] + 2, max(1, box[1] - 12))
                _heart(canvas, box[0] + box[2] + 5, max(1, box[1] - 12) + 3, (255, 90, 150))
        hop = 2 if i in (2, 3, 6, 7) else 0
        out.append(_frame(mood, theme, Pose(lift=hop, look_up=True, face=None if i < 10 else "sad"), ask))
    return out


def _ep_sulk(mood, theme):
    out = []
    for i in range(18):
        def cloud(canvas, box, i=i):
            cx = box[0] + box[2] // 2 - 6
            canvas.rect(cx, box[1] - 10, 12, 3, (110, 110, 130))
            canvas.rect(cx + 2, box[1] - 12, 7, 2, (110, 110, 130))
            for k in range(3):
                canvas.px(cx + 2 + k * 4, box[1] - 6 + (i + k * 2) % 6, _SWEAT)
        out.append(_frame(mood, theme, Pose(face="sad", squash=1, dx=0 if i % 9 else -1), cloud))
    return out


def _ep_explore(mood, theme, n=24):
    out = []
    for i in range(n):
        t = i / n
        dx = round(math.sin(math.tau * t) * 14)

        def clue(canvas, box, i=i):
            if 8 <= i < 16:
                x = box[0] + box[2] + 1
                canvas.rect(x, box[1] - 7, 3, 1, (255, 220, 80))
                canvas.px(x + 2, box[1] - 6, (255, 220, 80))
                canvas.px(x + 1, box[1] - 5, (255, 220, 80))
                canvas.px(x + 1, box[1] - 3, (255, 220, 80))
            if i >= 16:
                canvas.px(box[0] + box[2] // 2 + (i % 3) - 1, box[1] - 4 - (i % 4), theme.spark)
        out.append(_frame(mood, theme, Pose(dx=dx, squash=1 if 8 <= i < 16 and i % 2 else 0,
                                             look=1 if math.cos(math.tau * t) > 0 else -1, happy=i >= 16), clue))
    return out


def _ep_await(mood, theme, n=24):
    """Pad in hand, eyes on the screen: it knows you usually come to play about now."""
    out = []
    for i in range(n):
        def hope(canvas, box):
            x, y = box[0] + box[2] + 2, max(1, box[1] - 12)
            _bubble(canvas, x, y)
            canvas.rect(x + 3, y + 3, 5, 3, (170, 175, 195))
            canvas.px(x + 4, y + 4, (235, 50, 70))
            canvas.px(x + 6, y + 4, (90, 220, 110))
        pose = Pose(look=1, look_up=i % 12 < 8, lift=2 if i % 6 in (0, 1) and i >= 8 else 0, happy=i >= 16)
        out.append(_frame("play", theme, pose, hope if i >= 8 else None))
    return out


def _ep_impatient(mood, theme, n=20):
    out = []
    for i in range(n):
        def clock(canvas, box, i=i):
            x, y = box[0] + box[2] + 2, max(1, box[1] - 12)
            _bubble(canvas, x, y)
            canvas.circle(x + 5, y + 4, 3, (230, 230, 240))
            angle = math.tau * i / n
            canvas.line(x + 5, y + 4, x + 5 + round(math.cos(angle) * 2), y + 4 + round(math.sin(angle) * 2), (255, 214, 60))
        out.append(_frame(mood, theme, Pose(squash=1 if i % 4 < 2 else 0, look=(-1, 1)[i // 5 % 2], face="sad" if i > 10 else None), clock))
    return out


# While playing --------------------------------------------------------------------------------

def _ep_watch(mood, theme, n=20):
    out = []
    for i in range(n):
        tense = 8 <= i < 12
        out.append(_frame("play", theme, Pose(look=1 if i % 10 < 6 else -1, look_up=True, lift=2 if i in (12, 13) else 0,
                                               face="focused" if tense else None, happy=i in (12, 13, 14))))
    return out


def _ep_cheer(mood, theme, n=16):
    out = []
    for i in range(n):
        up = i % 4 < 2

        def stars(canvas, box, i=i):
            for k in range(3):
                canvas.px(box[0] - 3 + k * 14, box[1] - 4 - (i + k) % 5, theme.spark)
        out.append(_frame("idle", theme, Pose(lift=5 if up else 0, arms="up" if up else "out", happy=True), stars))
    return out


def _ep_shiver(mood, theme, n=20):
    out = []
    for i in range(n):
        def drop(canvas, box, i=i):
            canvas.px(box[0] - 1, box[1] + 3 + i % 6, _SWEAT)
        out.append(_frame("idle", theme, Pose(shake=1 if i % 2 else -1, face="scared", squash=1), drop))
    return out


def _ep_zoom(mood, theme, n=22):
    out = []
    for i in range(n):
        dx = -44 + i * 4

        def lines(canvas, box):
            for k, y in enumerate((box[1] + 4, box[1] + 9, box[1] + 13)):
                canvas.rect(box[0] - 10 - k * 2, y, 7, 1, scale(theme.soft, 0.8))
        out.append(_frame("idle", theme, Pose(dx=dx, look=1, band=True, face="focused", lift=1 if i % 2 else 0), lines))
    return out


def _ep_aim(mood, theme, n=20):
    out = []
    for i in range(n):
        t = i / n
        cx, cy = W // 2 + round(math.cos(math.tau * t) * 20), 10 + round(math.sin(math.tau * t * 2) * 4)

        def cross(canvas, box, cx=cx, cy=cy, i=i):
            colour = (255, 80, 80)
            canvas.rect(cx - 3, cy, 2, 1, colour)
            canvas.rect(cx + 2, cy, 2, 1, colour)
            canvas.rect(cx, cy - 3, 1, 2, colour)
            canvas.rect(cx, cy + 2, 1, 2, colour)
            if i % 5 == 4:
                canvas.circle(cx, cy, 2, (255, 230, 120))
        out.append(_frame("play", theme, Pose(look=1 if cx > W // 2 else -1, look_up=True, face="focused"), cross))
    return out


def _ep_sword(mood, theme, n=16):
    out = []
    for i in range(n):
        angle = -1.2 + (i % 8) / 7 * 2.4

        def blade(canvas, box, angle=angle, i=i):
            hx, hy = box[0] + box[2] + 1, box[1] + 9
            tip = (hx + round(math.cos(angle) * 9), hy - round(math.sin(-angle + 1.5) * 9))
            canvas.line(hx, hy, tip[0], tip[1], (220, 230, 255))
            canvas.px(hx, hy, (200, 140, 60))
            if i % 8 in (5, 6):
                canvas.px(tip[0] + 1, tip[1] - 1, theme.spark)
        out.append(_frame("idle", theme, Pose(look=1, face="focused" if i % 8 < 5 else None, happy=i % 8 >= 5,
                                               lift=1 if i % 8 == 5 else 0), blade))
    return out


def _ep_think(mood, theme, n=22):
    out = []
    for i in range(n):
        def idea(canvas, box, i=i):
            x, y = box[0] + box[2] + 2, max(1, box[1] - 12)
            _bubble(canvas, x, y)
            if i < 6:
                for k in range(1 + i % 3):
                    canvas.px(x + 3 + k * 2, y + 4, (230, 230, 240))
            elif i < 14:
                canvas.rect(x + 4, y + 2, 3, 1, (230, 230, 240))
                canvas.px(x + 6, y + 3, (230, 230, 240))
                canvas.px(x + 5, y + 4, (230, 230, 240))
                canvas.px(x + 5, y + 6, (230, 230, 240))
            else:
                canvas.circle(x + 5, y + 4, 2, (255, 230, 90), filled=True)
                canvas.px(x + 5, y + 7, (180, 180, 190))
        out.append(_frame(mood, theme, Pose(look_up=True, look=1, happy=i >= 14, lift=2 if i in (14, 15) else 0,
                                             face=None if i >= 14 else "focused"), idea))
    return out


def _ep_box(mood, theme, n=16):
    out = []
    for i in range(n):
        jab = i % 4

        def gloves(canvas, box, jab=jab):
            reach = (0, 4, 0, -4)[jab]
            canvas.rect(box[0] - 3 + min(0, reach), box[1] + 8, 3, 3, (230, 40, 50))
            canvas.rect(box[0] + box[2] + max(0, reach), box[1] + 8, 3, 3, (230, 40, 50))
        out.append(_frame("idle", theme, Pose(dx=(0, 1, 0, -1)[jab], band=True, face="focused", lift=1 if jab == 0 else 0), gloves))
    return out


def _ep_sweat(mood, theme, n=18):
    out = []
    for i in range(n):
        def drops(canvas, box, i=i):
            for k in range(3):
                phase = (i / n + k / 3) % 1.0
                canvas.px(box[0] - 2 - round(phase * 4), box[1] + 2 + round(phase * 10), _SWEAT)
                canvas.px(box[0] + box[2] + 1 + round(phase * 4), box[1] + 3 + round(phase * 9), _SWEAT)
        out.append(_frame("play", theme, Pose(face="scared" if i % 6 < 4 else "focused", shake=1 if i % 3 == 0 else 0), drops))
    return out


def _ep_fan_self(mood, theme, n=16):
    out = []
    for i in range(n):
        def fan(canvas, box, i=i):
            x, y = box[0] + box[2] + 3, box[1] + 4
            canvas.rect(x, y + 3, 1, 5, (150, 150, 170))
            blade = ((-2, 0), (2, 0)) if i % 2 else ((0, -2), (0, 2))
            for bx, by in blade:
                canvas.line(x, y, x + bx, y + by, (200, 230, 255))
            canvas.px(box[0] - 2, box[1] + 3 + i % 5, _SWEAT)
        out.append(_frame("hot", theme, Pose(look=1, squash=1 if i % 4 < 2 else 0), fan))
    return out


def _wind(canvas: Canvas, t: float, strong: bool = True) -> None:
    for k in range(7 if strong else 4):
        y = 4 + k * 6
        x = W - round(((t * 3 + k * 0.37) % 1.0) * (W + 20))
        canvas.rect(x, y, 9 if strong else 5, 1, (150, 170, 200))


def _ep_blown(mood, theme, n=40):
    out = []
    for i in range(n):
        t = i / n
        if i < 10:
            pose = Pose(squash=3, dx=-i // 3, face="scared", arms="out")
        elif i < 22:
            k = i - 10
            pose = Pose(dx=-4 - k * 5, lift=k * 1.6, squash=-2, face="scared", arms="up")
        elif i < 28:
            out.append(_frame_wind(t))
            continue
        else:
            k = i - 28
            pose = Pose(dx=40 - k * 4, lift=max(0, 6 - k), face="dizzy" if k < 8 else None, happy=k >= 10)
        out.append(_frame("idle", theme, pose, lambda canvas, box, t=t: _wind(canvas, t)))
    return out


def _frame_wind(t: float) -> Canvas:
    canvas = Canvas()
    _wind(canvas, t)
    return canvas


def _ep_hold(mood, theme, n=20):
    out = []
    for i in range(n):
        t = i / n
        out.append(_frame("idle", theme, Pose(squash=4 if i % 4 < 2 else 3, dx=-1 if i % 2 else 0, face="focused", arms="out"),
                          lambda canvas, box, t=t: _wind(canvas, t)))
    return out


# Night ----------------------------------------------------------------------------------------

_DREAMS = {
    "racing": ("..####..", ".######.", "########", ".#....#."),
    "horror": (".####.", "#.##.#", "######", "#.#.#."),
    "rpg": ("...#", "..#.", "##..", ".#.."),
    "shooter": ("#.....", "######", "####..", "#....."),
    "puzzle": ("##..", "##..", "####", "..##"),
}
_STAR_DREAM = ("..#..", ".###.", "#####", ".###.", ".#.#.")


def _ep_dream(mood, theme, n=24, favourite=None):
    art = _DREAMS.get(favourite or "", _STAR_DREAM)
    out = []
    for i in range(n):
        def dream(canvas, box, i=i):
            x, y = box[0] + box[2] + 1, max(1, box[1] - 13)
            if i >= 4:
                _bubble(canvas, x, y, 12, 10)
                for gy, row in enumerate(art):
                    for gx, cell in enumerate(row):
                        if cell == "#":
                            canvas.px(x + 2 + gx + (i // 3) % 2, y + 2 + gy, theme.spark)
            else:
                canvas.px(x - 1 + i, y + 9 - i, (200, 200, 220))
        out.append(_frame("sleep", theme, Pose(eyes_closed=True, squash=1 if i % 8 < 4 else 0, happy=i >= 8), dream))
    return out


def _ep_turn(mood, theme):
    poses = [Pose(eyes_closed=True, squash=s, dx=d) for s, d in ((0, 0), (2, 1), (3, 2), (2, 2), (1, 2), (0, 2))]
    poses += [Pose(eyes_closed=True, squash=s, dx=2) for s in (1, 0, 1, 0)]
    return [_frame("sleep", theme, pose) for pose in poses]


def _ep_snore(mood, theme, n=20):
    out = []
    for i in range(n):
        def zs(canvas, box, i=i):
            for k in range(2):
                phase = (i / n + k / 2) % 1.0
                _z(canvas, box[0] + box[2] + 1 + round(phase * 8), box[1] - 2 - round(phase * 16), 3 + k,
                   scale(theme.soft, 1 - phase * 0.6))
        out.append(_frame("sleep", theme, Pose(eyes_closed=True, squash=1 if i % 10 < 5 else -1, chomp=i % 10 >= 5), zs))
    return out


# Reactions ------------------------------------------------------------------------------------

def _ep_refuse(mood, theme):
    out = []
    for i in range(16):
        def apple(canvas, box, i=i):
            if i < 6:
                _apple(canvas, W // 2, -3 + i * 4)
            else:
                k = i - 6
                _apple(canvas, W // 2 + k * 4, 30 + round(abs(math.sin(k / 2)) * -6) + k)
        out.append(_frame(mood, theme, Pose(look=(-1, 1)[i // 2 % 2] if i >= 6 else 0, look_up=i < 6,
                                             face="sad" if i >= 6 else None), apple))
    return out


def _ep_purr(mood, theme, n=20):
    out = []
    for i in range(n):
        pat = i % 6

        def hand(canvas, box, pat=pat, i=i):
            y = box[1] - 6 + (pat if pat < 3 else 6 - pat)
            x = box[0] + box[2] // 2 - 5
            skin, crease = (255, 210, 180), (215, 160, 130)
            canvas.rect(x + 2, 0, 6, y - 1, skin)
            canvas.rect(x, y - 2, 10, 3, skin)
            for k in range(4):
                canvas.rect(x + k * 3, y + 1, 2, 2, skin)
            canvas.rect(x + 2, y - 3, 6, 1, crease)
            if i >= 8:
                _heart(canvas, box[0] + box[2] + 2, box[1] - 2 - (i % 5), (255, 90, 150))
        out.append(_frame(mood, theme, Pose(eyes_closed=True, happy=True, squash=1 if pat in (2, 3) else 0), hand))
    return out


def _ep_play(mood, theme):
    return _ep_ball(mood, theme) + _ep_hearts(mood, theme, 10)


def _ep_sleep(mood, theme):
    out = _ep_yawn(mood, theme)
    for k in range(8):
        frame = _frame("sleep", theme, Pose(eyes_closed=True, squash=2))
        dim = Canvas()
        for y in range(H):
            for x in range(W):
                dim.px(x, y, scale(frame.get(x, y), 1 - k * 0.08))
        out.append(dim)
    return out


def _ep_wake(mood, theme):
    out = [_frame(mood, theme, Pose(eyes_closed=True, squash=2 - k)) for k in range(4)]
    out += [_frame(mood, theme, Pose(squash=-2, arms="up", chomp=True)) for _ in range(3)]
    out += [_frame(mood, theme, Pose(happy=True, lift=lift)) for lift in (0, 3, 5, 3, 0)]
    return out


def _ep_tired(mood, theme):
    return _ep_yawn(mood, theme)[:8] + [_frame(mood, theme, Pose(face="sleepy", look=(-1, 1)[k % 2])) for k in range(6)]


def _ep_trophy(mood, theme, n=20):
    out = []
    for i in range(n):
        def cup(canvas, box, i=i):
            x, y = box[0] + box[2] // 2 - 3, box[1] - 9 - (1 if i % 4 < 2 else 0)
            gold = (255, 200, 60)
            canvas.rect(x, y, 7, 3, gold)
            canvas.rect(x + 1, y + 3, 5, 1, gold)
            canvas.rect(x + 3, y + 4, 1, 2, gold)
            canvas.rect(x + 1, y + 6, 5, 1, gold)
            canvas.px(x - 1, y + 1, gold)
            canvas.px(x + 7, y + 1, gold)
            for k in range(2):
                canvas.px(x - 3 + k * 12, y - 1 + (i + k * 2) % 4, theme.spark)
        out.append(_frame("idle", theme, Pose(arms="up", happy=True, lift=2 if i % 4 < 2 else 0), cup))
    return out


def _ep_greet(mood, theme, n=24):
    out = []
    for i in range(n):
        rise = min(1.0, i / 10)

        def sun(canvas):
            cy = 24 - round(rise * 16)
            canvas.circle(52, cy, 5, (255, 200, 70), filled=True)
            for k in range(8):
                angle = math.tau * k / 8 + i * 0.1
                canvas.px(52 + round(math.cos(angle) * 8), cy + round(math.sin(angle) * 8), (255, 170, 50))
        if i < 6:
            pose = Pose(eyes_closed=True, squash=2 - i // 3)
        elif i < 10:
            pose = Pose(squash=-2, arms="up", chomp=True)
        else:
            pose = Pose(happy=True, arms="up" if i % 4 < 2 else "out", look=1, lift=1 if i % 4 < 2 else 0)
        out.append(_frame(mood, theme, pose, behind=sun))
    return out


def _ep_scared(mood, theme):
    out = [_frame("idle", theme, Pose(face="scared", lift=6 - k * 2, arms="up")) for k in range(4)]
    out += _ep_shiver(mood, theme, 12)
    out += [_frame("idle", theme, Pose(dx=-k * 7, face="scared")) for k in range(6)]
    out += [Canvas()] * 3
    out += [_frame("idle", theme, Pose(dx=-34 + k * 3, face="scared", look=1)) for k in range(4)]
    out += [_frame("idle", theme, Pose(dx=-30 + k * 6, face="focused", look=1)) for k in range(6)]
    return out


def _ep_flinch(mood, theme):
    out = [_frame("idle", theme, Pose(face="scared", lift=3, arms="up")), _frame("idle", theme, Pose(face="scared", shake=1))]
    out += [_frame("idle", theme, Pose(face="focused", shake=(1, -1)[k % 2] if k < 4 else 0)) for k in range(8)]
    out += [_frame("play", theme, Pose(happy=True, look=1)) for _ in range(4)]
    return out


def _ep_party(mood, theme, n=32):
    palette = ((255, 90, 160), (90, 220, 255), (255, 220, 80), (140, 255, 140), (190, 120, 255))
    rng = random.Random(9)
    confetti = [(rng.randrange(W), rng.random()) for _ in range(26)]
    frames = []
    for i in range(n):
        t = i / n
        hop = abs(math.sin(math.tau * t * 2))

        def fall(canvas, box, t=t):
            for k, (x, phase) in enumerate(confetti):
                canvas.px(x, round(((t + phase) % 1.0) * (H + 4)) - 4, palette[k % len(palette)])
        frames.append(_frame("idle", theme, Pose(lift=hop * 9, squash=2 if hop < 0.15 else -1, happy=True, look_up=True), fall))
    return frames


def _ep_excited(mood, theme):
    return _ep_party(mood, theme, 16) + [_frame("idle", theme, Pose(face="love", lift=lift)) for lift in (0, 2, 4, 2, 0, 0)]


EPISODES: dict[str, Callable] = {
    "hop": _ep_hop, "dance": _ep_dance, "wander": _ep_wander, "stars": _ep_stars, "eat": _ep_apple,
    "ball": _ep_ball, "butterfly": _ep_butterfly, "nap": _ep_nap, "sneeze": _ep_sneeze, "peekaboo": _ep_peekaboo,
    "hearts": _ep_hearts, "wave": _ep_wave, "snack": _ep_snack, "hungry": _ep_hungry, "yawn": _ep_yawn,
    "call": _ep_call, "sulk": _ep_sulk, "explore": _ep_explore, "watch": _ep_watch, "cheer": _ep_cheer,
    "shiver": _ep_shiver, "zoom": _ep_zoom, "aim": _ep_aim, "sword": _ep_sword, "think": _ep_think, "box": _ep_box,
    "sweat": _ep_sweat, "fan_self": _ep_fan_self, "blown": _ep_blown, "hold": _ep_hold, "dream": _ep_dream,
    "turn": _ep_turn, "snore": _ep_snore, "refuse": _ep_refuse, "purr": _ep_purr, "play": _ep_play,
    "sleep": _ep_sleep, "wake": _ep_wake, "tired": _ep_tired, "trophy": _ep_trophy, "greet": _ep_greet,
    "scared": _ep_scared, "flinch": _ep_flinch, "party": _ep_party, "excited": _ep_excited,
    "await": _ep_await, "impatient": _ep_impatient,
}
REACTIONS = ("eat", "refuse", "play", "tired", "purr", "sleep", "snore", "wake", "trophy", "greet", "scared", "flinch",
             "party", "excited")


def episode_frames(name: str, mood: str, options: dict) -> list[tuple[Canvas, int]]:
    return [(canvas, _EPISODE_CS) for canvas in EPISODES[name](mood, theme_for(options))]


def _draw_mood(situation: str) -> str:
    if situation == "night":
        return "sleep"
    if situation == "hot":
        return "hot"
    if situation.startswith("game"):
        return "play"
    return "idle"


class PetScene(Scene):
    id = "pet"
    UPLOADS_PER_HOUR = 12
    OPTIONS = ("care", "theme")

    def __init__(self, mind: Mind | None = None):
        self.mind = mind or Mind(None)
        self._situation: str | None = None
        self._since = 0.0
        self._hot = False
        self._windy = False
        self._was_night = False
        self._playing = False
        self._slot_seen: str | None = None
        self._greet_slot: str | None = None

    def _genre(self, ctx: SceneContext) -> str | None:
        info = ctx.events.get("game_info") if isinstance(ctx.events, dict) else None
        game = ctx.game or {}
        if not isinstance(info, dict) or str(info.get("appid")) != str(game.get("appid")):
            return None
        return genre_for(info.get("tags"))

    def situation(self, ctx: SceneContext) -> str:
        temp, fan = ctx.metrics.get("gpu_temp"), ctx.metrics.get("fan_pct")
        if isinstance(temp, (int, float)):
            self._hot = temp >= _HOT_ENTER or (self._hot and temp > _HOT_EXIT)
        if isinstance(fan, (int, float)):
            self._windy = fan >= _WIND_ENTER or (self._windy and fan > _WIND_EXIT)
        if self.mind.asleep() and not ctx.game:
            return "night"
        if self._windy:
            return "windy"
        if self._hot:
            return "hot"
        if ctx.game:
            return f"game:{self._genre(ctx) or ''}"
        return "home"

    def key(self, ctx: SceneContext):
        wanted = self.situation(ctx)
        slot = _slot(ctx)
        playing = bool(ctx.game)
        if self._situation is None:
            self._situation, self._since = wanted, ctx.now
        elif wanted != self._situation:
            # Hot and windy start at once (at most every few minutes) but only end with the
            # window, so a fan hovering on a threshold cannot rewrite the panel over and over.
            entering = wanted in ("hot", "windy") and ctx.now - self._since >= _DWELL_S
            if playing != self._playing or entering or slot != self._slot_seen or "night" in (wanted, self._situation):
                self._situation, self._since = wanted, ctx.now
        self._playing = playing
        if self._situation == "night":
            self._was_night = True
        elif self._was_night:
            self._was_night, self._greet_slot = False, slot
        self._slot_seen = slot
        game = ctx.game or {}
        session = (game.get("appid"), game.get("started_at")) if game else None
        return self._situation, slot, ctx.options.get("theme"), self.mind.memory["revision"], session

    def _start(self, ctx: SceneContext) -> str | None:
        game = ctx.game or {}
        started = game.get("started_at")
        if not isinstance(started, (int, float)) or not 0 <= ctx.now - started < _REACTION_S:
            return None
        genre = self._genre(ctx)
        if genre == "horror":
            return "scared" if self.mind.fear(genre) >= _FRIGHT else "flinch"
        if genre and genre == self.mind.favourite() or self._expect(ctx, started) >= 0.5:
            return "excited"
        return "party"

    def _expect(self, ctx: SceneContext, at: float) -> float:
        local = datetime.fromtimestamp(at, ctx.tz)
        return self.mind.expectation(local.weekday() * 24 + local.hour, ctx.now)

    def face(self, ctx: SceneContext) -> str | None:
        needs = self.mind.needs(ctx.now)
        if needs["love"] < 0.25 or needs["hunger"] < 0.2:
            return "sad"
        if needs["energy"] < 0.3:
            return "sleepy"
        return None

    def _head(self, ctx: SceneContext) -> str | None:
        fresh = self.mind.recent(ctx.now)
        if fresh in EPISODES:
            return fresh
        start = self._start(ctx)
        if start:
            return start
        if self._greet_slot == _slot(ctx) and self._situation == "home":
            return "greet"
        return None

    def script(self, ctx: SceneContext) -> list[tuple[str, float]]:
        situation = self._situation or self.situation(ctx)
        start, end = _window(ctx)
        now = datetime.fromtimestamp(ctx.now, ctx.tz)
        remaining = max(1.0, (end - now).total_seconds())
        rng = random.Random(f"{start.timestamp()}:{situation}:{self.mind.memory['revision']}")
        head = self._head(ctx)
        expect = self._expect(ctx, ctx.now) if situation == "home" else 0.0
        plan = self.mind.plan(ctx.now, remaining - (4 if head else 0), situation=situation, rng=rng, expect=expect)
        if head:
            plan = [(head, 0.5)] + [(name, rng.uniform(3, 6) if i == 0 else rest) for i, (name, rest) in enumerate(plan)]
        return plan or [("hop", 0.5)]

    def _episode(self, name: str, mood: str, theme) -> list[Canvas]:
        if name == "dream":
            return _ep_dream(mood, theme, favourite=self.mind.favourite())
        return EPISODES[name](mood, theme)

    def render(self, ctx: SceneContext) -> Segment:
        if self._situation is None:
            self.key(ctx)
        situation = self._situation
        theme = theme_for(ctx.options)
        _start, end = _window(ctx)
        now = datetime.fromtimestamp(ctx.now, ctx.tz)
        remaining_cs = round((end - now).total_seconds() * 100)
        script = self.script(ctx)
        face = None if situation == "night" else self.face(ctx)
        while True:
            segment = self._life(situation, theme, script, remaining_cs, end.timestamp(), face)
            if fits(segment) or len(script) <= 2:
                return segment
            script = _thinned(script)

    def _life(self, situation: str, theme, script, total_cs: int, until: float, face: str | None) -> Segment:
        mood = _draw_mood(situation)
        asleep = situation == "night"
        rest = _frame(mood, theme, Pose(eyes_closed=asleep, face=face))
        blink = _frame(mood, theme, Pose(blink=True))
        glance = _frame(mood, theme, Pose(look=-1, eyes_closed=asleep, face=face))
        frames: list[Canvas] = [rest]
        delays: list[int] = [100]
        for name, rest_s in script:
            rest_cs = round(rest_s * 100)
            while rest_cs > 0:
                hold = min(rest_cs, 350)
                frames.append(rest)
                delays.append(hold)
                rest_cs -= hold
                if rest_cs > 0 and not asleep:
                    quick = len(frames) % 3 != 0
                    frames.append(blink if quick else glance)
                    delays.append(15 if quick else 80)
                    rest_cs -= delays[-1]
            for canvas in self._episode(name, mood, theme):
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

    def preview(self, ctx: SceneContext) -> Segment:
        """A montage of what the pet is about to get up to, instead of its first seconds of rest."""
        if self._situation is None:
            self.key(ctx)
        mood = _draw_mood(self._situation or "home")
        theme = theme_for(ctx.options)
        frames: list[Canvas] = []
        for name, _rest in self.script(ctx)[:4]:
            frames += self._episode(name, mood, theme)
        return Segment(frames, [_EPISODE_CS] * len(frames))

    def asleep(self, options: dict) -> Segment:
        """What stays on the panel while the Steam Machine is suspended."""
        theme = theme_for(options)
        frames = _ep_snore("sleep", theme)
        return Segment(frames, [12] * len(frames))


def _thinned(script: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Every other action, folding the dropped one's time into the next rest; the head stays."""
    out = [script[0]]
    for index in range(1, len(script), 2):
        name, rest = script[index]
        if index + 1 < len(script):
            rest += script[index + 1][1] + 2
        out.append((name, rest))
    return out


def _window(ctx: SceneContext) -> tuple[datetime, datetime]:
    now = datetime.fromtimestamp(ctx.now, ctx.tz)
    start = now.replace(minute=(now.minute // _SCRIPT_MINUTES) * _SCRIPT_MINUTES, second=0, microsecond=0)
    return start, start + timedelta(minutes=_SCRIPT_MINUTES)


def _slot(ctx: SceneContext) -> str:
    return _window(ctx)[0].isoformat()
