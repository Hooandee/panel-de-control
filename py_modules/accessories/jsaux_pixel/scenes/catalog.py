"""Every scene Panel offers for the panel, with its gallery category."""

from . import art, clocks, firmware, game, performance, pet, signature
from ..library import Library
from .composed import ComposedScene
from .custom import CustomScene
from .. import weather
from .base import Scene

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build(library: Library) -> list[tuple[str, Scene]]:
    return [
        *(("art", scene) for scene in signature.SCENES),
        *(("living", scene) for scene in pet.SCENES),
        ("living", weather.WeatherScene(weather.WeatherSource())),
        *(("clocks", scene) for scene in clocks.SCENES),
        *(("game", scene) for scene in game.SCENES + performance.SCENES),
        *(("art", scene) for scene in art.SCENES),
        *(("firmware", scene) for scene in firmware.SCENES),
        ("custom", CustomScene(library)),
        ("custom", ComposedScene(library)),
    ]
