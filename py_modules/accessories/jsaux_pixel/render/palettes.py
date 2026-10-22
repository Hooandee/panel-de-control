"""Colour themes for scenes. Values stay dim enough that the light budget rarely has to step in."""

from dataclasses import dataclass

Rgb = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    start: Rgb
    end: Rgb
    soft: Rgb
    dim: Rgb
    spark: Rgb


THEMES = {
    "aurora": Theme((176, 120, 255), (64, 220, 255), (150, 140, 230), (34, 30, 52), (255, 120, 190)),
    "sunset": Theme((255, 150, 60), (255, 70, 120), (230, 150, 120), (52, 28, 26), (255, 214, 90)),
    "mint": Theme((90, 240, 170), (60, 170, 255), (130, 210, 180), (20, 46, 40), (220, 255, 120)),
    "mono": Theme((235, 232, 250), (200, 196, 225), (170, 166, 190), (36, 34, 42), (255, 255, 255)),
}
DEFAULT_THEME = "aurora"


def theme_for(options: dict) -> Theme:
    return THEMES.get(str(options.get("theme", DEFAULT_THEME)), THEMES[DEFAULT_THEME])


def mix(a: Rgb, b: Rgb, t: float) -> Rgb:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def scale(rgb: Rgb, k: float) -> Rgb:
    return tuple(max(0, min(255, round(c * k))) for c in rgb)
