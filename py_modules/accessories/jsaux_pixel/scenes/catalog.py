"""Every scene Panel offers for the panel, with its gallery category."""

from . import art, clocks, firmware, signature
from .base import Scene

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build() -> list[tuple[str, Scene]]:
    return [
        *(("art", scene) for scene in signature.SCENES),
        *(("clocks", scene) for scene in clocks.SCENES),
        *(("art", scene) for scene in art.SCENES),
        *(("firmware", scene) for scene in firmware.SCENES),
    ]
