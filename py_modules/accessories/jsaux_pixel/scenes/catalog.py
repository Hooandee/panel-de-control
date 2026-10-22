"""Every scene Panel offers for the panel, with its gallery category."""

from . import clocks, firmware
from .base import Scene

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build() -> list[tuple[str, Scene]]:
    return [
        *(("clocks", scene) for scene in clocks.SCENES),
        *(("firmware", scene) for scene in firmware.SCENES),
    ]
