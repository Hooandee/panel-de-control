"""Every scene Panel offers for the panel, with its gallery category."""

from . import firmware
from .base import Scene

CATEGORIES = ("clocks", "living", "game", "panel", "art", "firmware", "custom")


def build() -> list[tuple[str, Scene]]:
    return [("firmware", scene) for scene in firmware.SCENES]
