"""Every scene Panel offers for the panel, with its gallery category."""

from . import art, clocks, firmware, game, performance, pet, signature
from .. import weather
from .base import Scene

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build() -> list[tuple[str, Scene]]:
    return [
        *(("art", scene) for scene in signature.SCENES),
        *(("living", scene) for scene in pet.SCENES),
        ("living", weather.WeatherScene(weather.WeatherSource())),
        *(("clocks", scene) for scene in clocks.SCENES),
        *(("game", scene) for scene in game.SCENES + performance.SCENES),
        *(("art", scene) for scene in art.SCENES),
        *(("firmware", scene) for scene in firmware.SCENES),
    ]
