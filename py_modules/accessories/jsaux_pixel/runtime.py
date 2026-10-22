"""Glue between Panel de Control and the JSAUX PIXEL service."""

import base64
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import detect, metrics, transport
from .render.canvas import quantize
from .scenes import catalog
from .scenes.base import SceneContext
from .service import PixelService, Worker

SUPPORTED_DEVICES = frozenset({"steam_machine"})
PREVIEW_MAX_FRAMES = 64
_FPS_SCENES = frozenset({"game_heart", "game_dashboard"})
_ART_BYTES = 64 * 54 * 3


class Runtime:
    def __init__(self, *, settings_dir: Path, device_key: str | None, log: Callable[..., None],
                 find_panel: Callable[[], detect.PanelPort | None] = detect.find_panel,
                 context_source: Callable[[], dict] | None = None,
                 system_metrics: Callable[[], dict] | None = None):
        self.supported = device_key in SUPPORTED_DEVICES
        self._entries = catalog.build()
        self._context_source = context_source or (lambda: {})
        self._system_metrics = system_metrics or metrics.SystemMetrics().sample
        self._events: dict = {}
        self.service = PixelService(
            store_path=Path(settings_dir) / "accessories" / "jsaux_pixel.json",
            find_panel=find_panel,
            open_link=lambda port: transport.Transport(port.dev),
            port_holders=detect.port_holders,
            scenes={scene.id: scene for _, scene in self._entries},
            context=self._context,
            log=log,
            enabled=self.supported,
        )
        self.worker: Worker | None = None

    def start(self) -> None:
        if self.supported and self.worker is None:
            self.worker = Worker(self.service)
            self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker = None

    def state(self) -> dict:
        state = self.service.state()
        state["supported"] = self.supported
        state["catalog"] = [
            {"id": scene.id, "category": category, "labelKey": f"accessories.scene.{scene.id}"}
            for category, scene in self._entries
        ]
        return state

    def set_scene(self, scene_id: str, options: dict) -> dict:
        self.service.set_scene(scene_id, options)
        return self.state()

    def set_brightness(self, percent: int) -> dict:
        self.service.set_brightness(percent)
        return self.state()

    def set_power(self, on: bool) -> dict:
        self.service.set_power(on)
        return self.state()

    def wants_fps(self) -> bool:
        return self.service.state()["scene"] in _FPS_SCENES

    def notify(self, name: str, data: dict) -> bool:
        if name != "game_art" or not isinstance(data, dict):
            return False
        try:
            valid = len(base64.b64decode(str(data.get("rgb") or ""), validate=True)) == _ART_BYTES
        except ValueError:
            valid = False
        if not valid:
            return False
        self._events = {**self._events, "game_art": {"appid": str(data.get("appid")), "rgb": data["rgb"]}}
        return True

    def preview(self, scene_id: str, options: dict) -> dict:
        if scene_id not in {scene.id for _, scene in self._entries}:
            raise ValueError(f"unknown scene {scene_id!r}")
        segment = self.service.preview(scene_id, options)
        if segment.firmware_animation is not None:
            return {"palette": [], "frames": [], "delays": [], "firmwareAnimation": segment.firmware_animation}
        frames = segment.frames[:PREVIEW_MAX_FRAMES]
        palette, indexed = quantize(frames)
        return {
            "palette": [list(rgb) for rgb in palette],
            "frames": [base64.b64encode(ix).decode("ascii") for ix in indexed],
            "delays": list(segment.delays_cs[:len(frames)]),
            "firmwareAnimation": None,
        }

    def _context(self, now: float) -> SceneContext:
        extra = self._context_source() or {}
        readings = {key: value for key, value in (self._system_metrics() or {}).items() if value is not None}
        readings.update({key: value for key, value in (extra.get("metrics") or {}).items() if value is not None})
        return SceneContext(
            now=now,
            tz=datetime.now().astimezone().tzinfo,
            game=extra.get("game"),
            metrics=readings,
            events=self._events,
        )

