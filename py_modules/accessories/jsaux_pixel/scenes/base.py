"""What a scene gives the scheduler: frames to precompute and how long they stay right."""

from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any, Hashable

from ..render.canvas import Canvas


@dataclass(frozen=True)
class SceneContext:
    now: float
    options: dict = field(default_factory=dict)
    tz: tzinfo | None = None
    game: dict | None = None
    metrics: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)


@dataclass
class Segment:
    frames: list[Canvas]
    delays_cs: list[int]
    valid_until: float | None = None
    kind: str = "scheduled"
    metric: str | None = None
    firmware_animation: int | None = None
    ready: bool = True


class Scene:
    """A scene re-renders only when `key` changes or its segment expires.

    UPLOADS_PER_HOUR is the steady-state write cost the scene is designed for; tests hold each
    scene to it.
    """

    id: str = ""
    UPLOADS_PER_HOUR: float = 0
    OPTIONS: tuple[str, ...] = ()
    SETTLE = False

    def key(self, ctx: SceneContext) -> Hashable:
        return None

    def render(self, ctx: SceneContext) -> Segment:
        raise NotImplementedError

    def preview(self, ctx: SceneContext) -> Segment:
        return self.render(ctx)

    def describe(self) -> dict[str, Any]:
        return {"id": self.id}
