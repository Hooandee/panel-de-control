"""Glue between Panel de Control and the JSAUX PIXEL service."""

import base64
import time
import json
import os
import pwd
import subprocess
from collections.abc import Callable
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

from controllers.detect import clean_env

from . import detect, metrics, transport, weather
from .library import Library
from .render.canvas import quantize
from .scenes import catalog
from .scenes.base import SceneContext
from .scenes.pet_mind import Mind, genre_for
from .service import PixelService, Worker

SUPPORTED_DEVICES = frozenset({"steam_machine"})
PREVIEW_MAX_FRAMES = 64
_FPS_SCENES = frozenset({"game_heart", "game_dashboard"})
_ART_BYTES = 64 * 54 * 3
_PORTRAIT_BYTES = 36 * 54 * 3
_IMAGE_TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_IMAGE_LIMIT = 4 * 1024 * 1024
_OFFICIAL_SERVICE = "jsaux-matrix-hub.service"
_OFFICIAL_RECHECK_S = 60.0
_PET_BEDTIME = frozenset({23, 0, 1, 2, 3, 4, 5, 6})
_MAX_TAGS = 20


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
                 user: str = "deck", uid: int | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 localtime: Path | str = "/etc/localtime"):
        self.supported = device_key in SUPPORTED_DEVICES
        self._colores_state = Path(settings_dir).parent / "Colores" / "state.json"
        self._library = Library(Path(settings_dir) / "accessories" / "library")
        self._home = Path(user_home).resolve()
        self.mind = Mind(Path(settings_dir) / "accessories" / "pet.json")
        self._entries = catalog.build(self._library, self.mind)
        self._run = run or _run
        self._user, self._uid = user, uid if uid is not None else _uid_of(user)
        self._monotonic = monotonic
        self._localtime = Path(localtime)
        self._zone: tuple[str, tzinfo] | None = None
        self._official: tuple[float, bool] | None = None
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
            option_extras=self._option_extras,
            official_active=self.official_active,
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
            for category, scene in self._entries if category != "hidden"
        ]
        return state

    def set_scene(self, scene_id: str, options: dict) -> dict:
        self.service.set_scene(scene_id, options)
        return self.state()

    def set_brightness(self, percent: int) -> dict:
        self.service.set_brightness(percent)
        return self.state()

    def set_game_scene(self, scene_id: str | None) -> dict:
        self.service.set_game_scene(scene_id)
        return self.state()

    def set_night(self, night: dict) -> dict:
        self.service.set_night(night)
        return self.state()

    def set_power(self, on: bool) -> dict:
        self.service.set_power(on)
        return self.state()

    def set_on_suspend(self, mode: str) -> dict:
        self.service.set_on_suspend(mode)
        return self.state()

    def suspend(self) -> dict:
        pet = next(scene for _, scene in self._entries if scene.id == "pet")
        options = self.service.wanted_scenes()[3] if self.service.wanted_scenes()[0] == "pet" else {}
        self.service.suspend(lambda: pet.asleep({**options, **self._option_extras(options)}))
        return self.state()

    def resume(self) -> dict:
        self.service.resume()
        return self.state()

    def pet_state(self) -> dict:
        return self.mind.describe(time.time())

    def pet_action(self, kind: str) -> dict:
        reaction = self.mind.interact(kind, time.time())
        scene, showing, _game, _options = self.service.wanted_scenes()
        if "pet" in (scene, showing):
            self.service.forget_shown()
        self._log("INFO", "pet_action", kind=kind, reaction=reaction)
        return {"reaction": reaction, "pet": self.pet_state()}

    def rename_pet(self, name: str) -> dict:
        self.mind.rename(name)
        return self.pet_state()

    def ledbar_colors(self) -> list[list[int]] | None:
        """Read-only view of the colours Colores is showing on the Steam Machine's LED bar."""
        try:
            state = json.loads(self._colores_state.read_text())
        except (OSError, ValueError):
            return None

        def rgb(value) -> list[int] | None:
            if isinstance(value, list) and len(value) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in value):
                return list(value)
            return None

        gradient = [rgb(stop) for stop in state.get("gradient") or []] if isinstance(state, dict) else []
        solid = rgb(state.get("color")) if isinstance(state, dict) else None
        if state.get("mode") != "color" and len(gradient) >= 2 and all(gradient):
            return gradient
        return [solid, solid] if solid else None

    def _option_extras(self, options: dict) -> dict:
        if options.get("theme") != "ledbar":
            return {}
        colors = self.ledbar_colors()
        return {"ledbar": colors} if colors else {}

    def _user_systemctl(self, *args: str) -> int:
        env = {**clean_env(), "XDG_RUNTIME_DIR": f"/run/user/{self._uid}",
               "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{self._uid}/bus"}
        return self._run(["runuser", "-u", self._user, "--", "systemctl", "--user", *args], env)

    def official_active(self) -> bool:
        now = self._monotonic()
        if self._official is None or now - self._official[0] >= _OFFICIAL_RECHECK_S:
            self._official = (now, self._user_systemctl("is-active", _OFFICIAL_SERVICE) == 0)
        return self._official[1]

    def pause_official_app(self) -> dict:
        if not self.supported:
            return {"ok": False}
        code = self._user_systemctl("disable", "--now", _OFFICIAL_SERVICE)
        self._log("INFO" if code == 0 else "WARNING", "official_app_paused", code=code)
        if code == 0:
            self._official = (self._monotonic(), False)
            self.service.forget_shown()
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
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return {"ok": False, "error": "unreadable"}
        try:
            opened, checked = os.fstat(fd), os.stat(target, follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
                return {"ok": False, "error": "unsupported"}
            if opened.st_size > _IMAGE_LIMIT:
                return {"ok": False, "error": "too_large"}
            with os.fdopen(os.dup(fd), "rb") as handle:
                data = handle.read(_IMAGE_LIMIT + 1)
            return {"ok": True, "mime": mime, "data": base64.b64encode(data).decode("ascii")}
        except OSError:
            return {"ok": False, "error": "unreadable"}
        finally:
            os.close(fd)

    def search_cities(self, query: str, language: str) -> dict:
        return {"cities": weather.search_cities(query, language) if query.strip() else []}

    def locate_city(self) -> dict:
        if not self.supported:
            return {"city": None}
        return {"city": weather.locate(zone=str(self._local_zone()))}

    def wants_fps(self, playing: bool) -> bool:
        if not playing:
            return False
        scene, showing, game_scene, options = self.service.wanted_scenes()
        if {scene, showing, game_scene} & _FPS_SCENES:
            return True
        blocks = ((options or {}).get("layout") or {}).get("blocks") if scene == "composed" else None
        return any(isinstance(b, dict) and b.get("metric") == "fps" for b in blocks or [])

    def set_alerts(self, prefs: dict) -> dict:
        self.service.set_alerts(prefs)
        return self.state()

    def notify(self, name: str, data: dict | None) -> bool:
        if name == "download":
            event = None
            if isinstance(data, dict) and isinstance(data.get("total"), (int, float)) and data["total"] > 0:
                event = {"name": str(data.get("name") or "")[:40], "done": float(data.get("done") or 0),
                         "total": float(data["total"]), "seconds": float(data.get("seconds") or 0),
                         "paused": bool(data.get("paused"))}
            self._events = {**self._events, "download": event}
            return True
        if name == "achievement" and isinstance(data, dict):
            if not self.service.alert_enabled("achievements"):
                return False
            icon = data.get("icon") if isinstance(data.get("icon"), str) else None
            self.service.show_alert("alert", {"kind": name, "title": str(data.get("title") or "")[:40], "icon": icon})
            self.mind.achievement(time.time())
            self._log("INFO", "alert", kind=name)
            return True
        if name == "game_info":
            return self._game_info(data)
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

    def _game_info(self, data) -> bool:
        if not isinstance(data, dict) or not data.get("appid") or not isinstance(data.get("tags"), list):
            return False
        tags = [tag for tag in data["tags"][:_MAX_TAGS] if isinstance(tag, int)]
        achievements = data.get("achievements")
        done = achievements.get("done") if isinstance(achievements, dict) else None
        total = achievements.get("total") if isinstance(achievements, dict) else None
        playtime = data.get("playtime_min")
        info = {
            "appid": str(data["appid"]),
            "tags": tags,
            "playtime_min": int(playtime) if isinstance(playtime, (int, float)) and playtime >= 0 else None,
            "achievements": {"done": int(done), "total": int(total)}
            if isinstance(done, int) and isinstance(total, int) and 0 <= done <= total and total > 0 else None,
        }
        portrait = data.get("portrait")
        if isinstance(portrait, str):
            try:
                if len(base64.b64decode(portrait, validate=True)) == _PORTRAIT_BYTES:
                    info["portrait"] = portrait
            except ValueError:
                pass
        self._events = {**self._events, "game_info": info}
        game = (self._context_source() or {}).get("game") or {}
        if str(game.get("appid")) == info["appid"] and isinstance(game.get("started_at"), (int, float)):
            self.mind.saw_game(info["appid"], genre_for(tags), game["started_at"])
        return True

    def preview(self, scene_id: str, options: dict) -> dict:
        if scene_id not in {scene.id for _, scene in self._entries}:
            raise ValueError(f"unknown scene {scene_id!r}")
        segment = self.service.preview(scene_id, options)
        if segment.firmware_animation is not None:
            return {"palette": [], "frames": [], "delays": [], "firmwareAnimation": segment.firmware_animation, "ready": True}
        frames = segment.frames[:PREVIEW_MAX_FRAMES]
        palette, indexed = quantize(frames)
        return {
            "palette": [list(rgb) for rgb in palette],
            "frames": [base64.b64encode(ix).decode("ascii") for ix in indexed],
            "delays": list(segment.delays_cs[:len(frames)]),
            "firmwareAnimation": None,
            "ready": segment.ready,
        }

    def _local_zone(self) -> tzinfo:
        """The zone Steam's clock uses right now; glibc caches it at start, so read the link."""
        try:
            target = os.readlink(self._localtime)
        except OSError:
            return datetime.now().astimezone().tzinfo
        if self._zone and self._zone[0] == target:
            return self._zone[1]
        name = target.split("zoneinfo/", 1)[-1]
        try:
            zone: tzinfo = ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            zone = datetime.now().astimezone().tzinfo
        self._zone = (target, zone)
        return zone

    def _context(self, now: float) -> SceneContext:
        extra = self._context_source() or {}
        zone = self._local_zone()
        hour = datetime.fromtimestamp(now, zone).hour
        self.mind.observe(now, night=hour in _PET_BEDTIME, playing=bool(extra.get("game")))
        readings = {key: value for key, value in (self._system_metrics() or {}).items() if value is not None}
        readings.update({key: value for key, value in (extra.get("metrics") or {}).items() if value is not None})
        return SceneContext(
            now=now,
            tz=zone,
            game=extra.get("game"),
            metrics=readings,
            events=self._events,
        )

