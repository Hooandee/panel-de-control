"""Hooandee's signature scene: the wordmark with a travelling shine over a living aurora."""

import math
import random

from .. import codec
from ..render import fonts
from ..render.canvas import Canvas
from ..render.palettes import mix, scale
from .art import Loop

W, H = codec.WIDTH, codec.HEIGHT

_LETTERS = {
    "H": ("##...##", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##", "##...##"),
    "O": (".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."),
    "A": ("..###..", ".##.##.", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"),
    "N": ("##...##", "###..##", "###..##", "####.##", "##.####", "##..###", "##..###", "##...##", "##...##", "##...##", "##...##"),
    "D": ("#####..", "##..##.", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##..##.", "#####.."),
    "E": ("#######", "##.....", "##.....", "##.....", "######.", "######.", "##.....", "##.....", "##.....", "##.....", "#######"),
}
_WORD = "HOOANDEE"
_WORD_Y = 15
_VIOLET = (170, 110, 255)
_CYAN = (60, 220, 255)
_PINK = (255, 90, 190)


def _word_pixels() -> list[tuple[int, int]]:
    pixels, x = [], 0
    for letter in _WORD:
        for dy, row in enumerate(_LETTERS[letter]):
            for dx, cell in enumerate(row):
                if cell == "#":
                    pixels.append((x + dx, _WORD_Y + dy))
        x += 8
    return pixels


class SignatureScene(Loop):
    id = "hooandee"
    FRAMES = 40
    DELAY_CS = 6

    def __init__(self):
        rng = random.Random(2026)
        self.stars = [(rng.randrange(W), rng.randrange(0, 12), rng.random(), rng.choice((1, 2))) for _ in range(16)]
        self.word = _word_pixels()

    def frame(self, index, count, options):
        t = index / count
        canvas = Canvas()
        for x, y, phase, speed in self.stars:
            glow = 0.5 + 0.5 * math.sin(math.tau * (t * speed + phase))
            if glow > 0.25:
                canvas.px(x, y, scale((210, 200, 255), 0.25 + 0.75 * glow))
        sweep = -14 + t * (W + 28)
        for x, y in self.word:
            base = mix(_VIOLET, _CYAN, x / (W - 1))
            shine = max(0.0, 1 - abs((x + (y - _WORD_Y) * 0.6) - sweep) / 5)
            canvas.px(x, y, mix(base, (255, 255, 255), shine * 0.85))
        label = "PANEL DE CONTROL"
        lx = (W - fonts.measure(label, fonts.TINY)) // 2
        canvas.text(lx, 30, label, fonts.TINY, (150, 140, 210))
        light = [[0.0, 0.0, 0.0] for _ in range(W * H)]
        for wave, (amp, cycles, speed, colour, base) in enumerate((
            (3.2, 1, 1, _VIOLET, 44), (2.6, 2, -1, _CYAN, 47), (2.0, 3, 2, _PINK, 50),
        )):
            for x in range(W):
                crest = base + amp * math.sin(math.tau * (x / W * cycles + t * speed + wave * 0.3))
                top = math.floor(crest)
                for row in range(top, min(H, top + 6)):
                    if row < 0:
                        continue
                    weight = (1.0, 0.55, 0.32, 0.18, 0.1, 0.05)[row - top]
                    cell = light[row * W + x]
                    for channel in range(3):
                        cell[channel] += colour[channel] * weight
        for y in range(38, H):
            for x in range(W):
                r, g, b = light[y * W + x]
                if r + g + b > 12:
                    canvas.px(x, y, (min(255, round(r)), min(255, round(g)), min(255, round(b))))
        return canvas


SCENES = [SignatureScene()]
