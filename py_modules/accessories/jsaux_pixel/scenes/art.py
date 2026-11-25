"""Living art that loops on the panel by itself: one upload, then zero writes.

Every motion is periodic over the loop length, so the last frame flows into the first.
"""

import math
import random

from .. import codec
from ..render.canvas import Canvas
from ..render.palettes import mix, scale, theme_for
from .base import Scene, SceneContext, Segment
from .fit import fits

W, H = codec.WIDTH, codec.HEIGHT


class Loop(Scene):
    UPLOADS_PER_HOUR = 0
    OPTIONS = ("theme",)
    FRAMES = 32
    DELAY_CS = 8
    seamless = True

    def key(self, ctx: SceneContext):
        return "loop"

    def frame(self, index: int, count: int, options: dict) -> Canvas:
        raise NotImplementedError

    def render(self, ctx: SceneContext) -> Segment:
        count = self.FRAMES
        while True:
            frames = [self.frame(i, count, ctx.options) for i in range(count)]
            segment = Segment(frames, [self.DELAY_CS] * count)
            if fits(segment) or count <= 12:
                return segment
            count = max(12, count * 3 // 4)


class Starfield(Loop):
    """Warp tunnel: each star flies out and re-enters exactly once per loop."""

    id = "art_starfield"
    FRAMES = 36
    DELAY_CS = 7

    def __init__(self):
        rng = random.Random(7)
        self.stars = [(rng.uniform(0, math.tau), rng.random(), rng.choice((1, 1, 2))) for _ in range(70)]

    def frame(self, index, count, options):
        theme = theme_for(options)
        canvas = Canvas()
        t = index / count
        for angle, phase, speed in self.stars:
            r = (phase + t * speed) % 1.0
            if r < 0.08:
                continue
            dist = 3 + (r ** 1.8) * 46
            colour = mix(theme.start, theme.spark if r > 0.7 else theme.end, r)
            colour = mix(colour, (255, 255, 255), max(0.0, r - 0.6))
            streak = max(1, round(r * r * 7))
            for k in range(streak):
                d = dist - k
                fade = 0.3 + 0.7 * r * (1 - k / streak)
                canvas.px(int(W / 2 + math.cos(angle) * d), int(H / 2 + math.sin(angle) * d * 0.85), scale(colour, fade))
        return canvas


class MatrixRain(Loop):
    id = "art_matrix"
    OPTIONS = ()
    FRAMES = 27
    DELAY_CS = 8

    def __init__(self):
        rng = random.Random(11)
        self.columns = [(x, rng.random(), rng.choice((1, 2)), rng.randint(5, 12)) for x in range(0, W, 2)]
        self.glyph_noise = [[rng.random() for _ in range(H)] for _ in range(W)]

    def frame(self, index, count, options):
        canvas = Canvas()
        t = index / count
        span = H + 14
        for x, phase, speed, length in self.columns:
            head = ((phase + t * speed) % 1.0) * span - 7
            for k in range(length):
                y = int(head) - k
                if 0 <= y < H:
                    if k == 0:
                        colour = (190, 255, 200)
                    else:
                        fade = 1 - k / length
                        flicker = 0.75 + 0.25 * self.glyph_noise[x][y]
                        colour = (0, round(170 * fade * flicker), round(60 * fade * flicker))
                    canvas.px(x, y, colour)
        return canvas


class LavaLamp(Loop):
    id = "art_lava"
    FRAMES = 30
    DELAY_CS = 11

    BLOBS = ((0.30, 1, 0.0, 9), (0.55, 1, 0.33, 8), (0.72, 2, 0.66, 7), (0.45, 1, 0.5, 6))

    def frame(self, index, count, options):
        theme = theme_for({**options, "theme": options.get("theme", "sunset")})
        canvas = Canvas()
        t = index / count
        blobs = []
        for x_pos, speed, phase, radius in self.BLOBS:
            angle = math.tau * (t * speed + phase)
            blobs.append((W * x_pos + 6 * math.sin(angle * 2), H / 2 + (H / 2 - 8) * math.sin(angle), radius))
        for y in range(H):
            for x in range(W):
                field = sum(r * r / ((x - bx) ** 2 + (y - by) ** 2 + 1) for bx, by, r in blobs)
                if field > 1.0:
                    glow = min(1.0, (field - 1.0) / 1.6)
                    colour = mix(theme.end, theme.start, y / H)
                    canvas.px(x, y, scale(colour, 0.45 + 0.55 * glow))
                elif field > 0.82:
                    canvas.px(x, y, scale(theme.dim, 1.6))
        return canvas


class Aquarium(Loop):
    id = "art_aquarium"
    OPTIONS = ()
    FRAMES = 40
    DELAY_CS = 10

    FISH = ((8, 1, (255, 140, 60), 0.0), (22, -1, (90, 200, 255), 0.4), (33, 1, (255, 220, 90), 0.7))

    def __init__(self):
        rng = random.Random(3)
        self.bubbles = [(rng.randint(4, W - 4), rng.random()) for _ in range(7)]
        self.weeds = [(x, rng.randint(8, 16)) for x in (6, 12, 47, 53, 58)]

    def frame(self, index, count, options):
        canvas = Canvas()
        t = index / count
        for y in range(H):
            canvas.rect(0, y, W, 1, (0, round(10 + 18 * y / H), round(26 + 30 * y / H)))
        for x in range(W):
            canvas.px(x, H - 1, (70, 58, 34))
            if (x * 7) % 5 < 2:
                canvas.px(x, H - 2, (58, 48, 28))
        for x, height in self.weeds:
            for k in range(height):
                sway = round(math.sin(math.tau * t + k * 0.35 + x) * (k / height) * 2)
                canvas.px(x + sway, H - 2 - k, (40, 150 - k * 4, 70))
        for y, direction, colour, phase in self.FISH:
            fx = ((phase + t * direction) % 1.0) * (W + 16) - 8
            wobble = round(math.sin(math.tau * (t * 2 + phase)) * 1)
            _fish(canvas, round(fx), y + wobble, direction, colour)
        for bx, phase in self.bubbles:
            by = H - 4 - ((phase + t) % 1.0) * (H - 6)
            wiggle = round(math.sin(math.tau * (t * 3 + phase)) * 1)
            canvas.px(bx + wiggle, round(by), (150, 210, 255))
        return canvas


def _fish(canvas: Canvas, x: int, y: int, direction: int, colour) -> None:
    body = ("..###..", ".#####.", "#######", ".#####.", "..###..")
    for dy, row in enumerate(body):
        for dx, cell in enumerate(row):
            if cell == "#":
                px = x + (dx if direction > 0 else 6 - dx)
                canvas.px(px, y + dy - 2, colour if dy != 2 else scale(colour, 1.15))
    tail_x = x - 2 if direction > 0 else x + 8
    for dy in (-2, -1, 0, 1, 2):
        if abs(dy) != 0:
            canvas.px(tail_x + (0 if abs(dy) == 2 else (1 if direction > 0 else -1)), y + dy, scale(colour, 0.7))
    eye_x = x + 5 if direction > 0 else x + 1
    canvas.px(eye_x, y - 1, (20, 20, 30))


class GameOfLife(Loop):
    """Conway's life on a torus from a fixed seed; it restarts when the loop ends."""

    id = "art_life"
    FRAMES = 48
    DELAY_CS = 12
    seamless = False

    def __init__(self):
        rng = random.Random(42)
        self.seed = {(x, y) for x in range(W) for y in range(H) if rng.random() < 0.28}

    def _generations(self, count: int) -> list[tuple[set, dict]]:
        cells, ages = set(self.seed), {}
        history = [(cells, ages)]
        for _ in range(count):
            neighbours: dict[tuple[int, int], int] = {}
            for x, y in cells:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx or dy:
                            key = ((x + dx) % W, (y + dy) % H)
                            neighbours[key] = neighbours.get(key, 0) + 1
            cells = {c for c, n in neighbours.items() if n == 3 or (n == 2 and c in cells)}
            ages = {c: ages.get(c, 0) + 1 for c in cells}
            history.append((cells, ages))
        return history

    def frame(self, index, count, options):
        if getattr(self, "_history_len", None) != count:
            self._history, self._history_len = self._generations(count), count
        theme = theme_for(options)
        cells, ages = self._history[index % len(self._history)]
        canvas = Canvas()
        for c in cells:
            age = ages.get(c, 0)
            canvas.px(c[0], c[1], scale(mix(theme.end, theme.start, min(1.0, age / 6)), 0.75))
        return canvas


SCENES = [Starfield(), MatrixRain(), LavaLamp(), Aquarium(), GameOfLife()]
