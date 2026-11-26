"""Every scene Panel offers for the panel, with its gallery category."""

from . import alerts, art, clocks, firmware, game, performance, pet, speedrun
from ..library import Library
from .composed import ComposedScene
from .custom import CustomScene
from .. import weather
from .base import Scene
from .pet_mind import Mind

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build(library: Library, pet_mind: Mind | None = None) -> list[tuple[str, Scene]]:
    return [
        ("living", pet.PetScene(pet_mind)),
        ("living", weather.WeatherScene(weather.WeatherSource())),
        *(("clocks", scene) for scene in clocks.SCENES),
        *(("game", scene) for scene in game.SCENES + performance.SCENES),
        ("game", alerts.DownloadScene()),
        ("game", speedrun.SpeedrunScene()),
        *(("art", scene) for scene in art.SCENES),
        *(("firmware", scene) for scene in firmware.SCENES),
        ("custom", CustomScene(library)),
        ("custom", ComposedScene(library)),
        ("hidden", alerts.AlertScene()),
    ]
