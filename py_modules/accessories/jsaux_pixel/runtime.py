"""Glue between Panel de Control and the JSAUX PIXEL service."""

import base64
import os
import pwd
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import detect, metrics, transport, weather
from .library import Library
from .render.canvas import quantize
from .scenes import catalog
from .scenes.base import SceneContext
from .service import PixelService, Worker

SUPPORTED_DEVICES = frozenset({"steam_machine"})
PREVIEW_MAX_FRAMES = 64
_FPS_SCENES = frozenset({"game_heart", "game_dashboard"})
_ART_BYTES = 64 * 54 * 3
_IMAGE_TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_IMAGE_LIMIT = 8 * 1024 * 1024
_OFFICIAL_SERVICE = "jsaux-matrix-hub.service"


def _uid_of(user: str) -> int:
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return 1000


def _run(argv: list[str], env: dict) -> int:
    try:
        return subprocess.run(argv, env=env, timeout=15, capture_output=True).returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


class Runtime:
    def __init__(self, *, settings_dir: Path, device_key: str | None, log: Callable[..., None],
                 find_panel: Callable[[], detect.PanelPort | None] = detect.find_panel,
                 context_source: Callable[[], dict] | None = None,
                 system_metrics: Callable[[], dict] | None = None,
                 user_home: Path | str = "/home/deck",
                 run: Callable[[list[str], dict], int] | None = None,
                 user: str = "deck", uid: int | None = None):
        self.supported = device_key in SUPPORTED_DEVICES
        self._library = Library(Path(settings_dir) / "accessories" / "library")
        self._home = Path(user_home).resolve()
        self._entries = catalog.build(self._library)
        self._run = run or _run
        self._user, self._uid = user, uid if uid is not None else _uid_of(user)
        self._log = log
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
            {"id": scene.id, "category": category, "labelKey": f"accessories.scene.{scene.id}",
             "options": list(scene.OPTIONS)}
            for category, scene in self._entries
        ]
        return state

    def set_scene(self, scene_id: str, options: dict) -> dict:
        self.service.set_scene(scene_id, options)
        return self.state()

    def set_brightness(self, percent: int) -> dict:
        self.service.set_brightness(percent)
        return self.state()

    def set_night(self, night: dict) -> dict:
        self.service.set_night(night)
        return self.state()

    def set_power(self, on: bool) -> dict:
        self.service.set_power(on)
        return self.state()

    def pause_official_app(self) -> dict:
        if not self.supported:
            return {"ok": False}
        env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{self._uid}",
               "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{self._uid}/bus"}
        argv = ["runuser", "-u", self._user, "--", "systemctl", "--user", "disable", "--now", _OFFICIAL_SERVICE]
        code = self._run(argv, env)
        self._log("INFO" if code == 0 else "WARNING", "official_app_paused", code=code)
        return {"ok": code == 0}

    def list_drawings(self) -> dict:
        return {"drawings": self._library.list()}

    def load_drawing(self, drawing_id: str) -> dict:
        try:
            drawing = self._library.load(drawing_id)
        except ValueError:
            drawing = None
        if not drawing:
            return {"ok": False}
        return {"ok": True, "id": drawing["id"], "name": drawing.get("name", ""), "frames": drawing["frames"],
                "fps": drawing.get("fps", 8)}

    def save_drawing(self, drawing: dict) -> dict:
        try:
            return {"ok": True, **self._library.save(drawing)}
        except (ValueError, KeyError) as error:
            return {"ok": False, "error": str(error)}

    def delete_drawing(self, drawing_id: str) -> dict:
        try:
            self._library.delete(drawing_id)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True}

    def read_image(self, path: str) -> dict:
        target = Path(path).resolve()
        mime = _IMAGE_TYPES.get(target.suffix.lower())
        if mime is None or self._home not in target.parents:
            return {"ok": False, "error": "unsupported"}
        try:
            if target.stat().st_size > _IMAGE_LIMIT:
                return {"ok": False, "error": "too_large"}
            return {"ok": True, "mime": mime, "data": base64.b64encode(target.read_bytes()).decode("ascii")}
        except OSError:
            return {"ok": False, "error": "unreadable"}

    def search_cities(self, query: str, language: str) -> dict:
        return {"cities": weather.search_cities(query, language) if query.strip() else []}

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

