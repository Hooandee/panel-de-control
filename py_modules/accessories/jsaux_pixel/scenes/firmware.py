"""The four animations stored in the panel firmware: shown without uploading any GIF."""

from .base import Scene, SceneContext, Segment


class FirmwareAnimation(Scene):
    UPLOADS_PER_HOUR = 0

    def __init__(self, scene_id: str, animation: int):
        self.id = scene_id
        self.animation = animation

    def key(self, ctx: SceneContext):
        return self.animation

    def render(self, ctx: SceneContext) -> Segment:
        return Segment([], [], firmware_animation=self.animation)


SCENES = [
    FirmwareAnimation("fw_tunnel", 0),
    FirmwareAnimation("fw_dodecahedron", 1),
    FirmwareAnimation("fw_fireworks", 2),
    FirmwareAnimation("fw_desert", 3),
]
