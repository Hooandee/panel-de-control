"""Keeps the panel showing the chosen scene with as few flash writes as possible.

`tick()` is one pass: connect when needed, re-render the scene only if its inputs changed or its
segment expired, and upload only what the governor and power guard allow. A worker thread calls
it; it never runs on the asyncio loop.
"""

import dataclasses
import hashlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from json_store import atomic_json_save

from . import codec, gif, power_guard
from .detect import PanelPort
from .governor import Decision, Governor
from .render.canvas import quantize
from .scenes.base import Scene, SceneContext, Segment
from .transport import TransportError

_RECONNECT_S = 5.0
_ACK_TIMEOUT_S = 2.0
_END_TIMEOUT_S = 3.0
_DEFAULT_BRIGHTNESS = 60


class PixelService:
    def __init__(self, *, store_path: Path, find_panel: Callable[[], PanelPort | None],
                 open_link: Callable[[PanelPort], object], port_holders: Callable[[str], list],
                 scenes: dict[str, Scene], context: Callable[[float], SceneContext],
                 log: Callable[..., None], clock: Callable[[], float] = time.time, enabled: bool = True):
        self._store_path = Path(store_path)
        self._find_panel, self._open_link, self._port_holders = find_panel, open_link, port_holders
        self._scenes, self._context, self._log, self._clock = scenes, context, log, clock
        self._enabled = enabled
        self._lock = threading.RLock()
        self._port: PanelPort | None = None
        self._link = None
        self._busy_by: str | None = None
        self._next_probe = 0.0
        self._rendered_key = None
        self._valid_until: float | None = None
        self._pending_user = True
        self._brightness_sent: int | None = None
        self._last_upload: dict | None = None
        stored = self._load()
        scene = stored.get("scene") if isinstance(stored.get("scene"), dict) else {}
        self._scene_id: str | None = scene.get("id") if scene.get("id") in scenes else None
        self._options = scene.get("options") if isinstance(scene.get("options"), dict) else {}
        brightness = stored.get("brightness")
        self._brightness = brightness if isinstance(brightness, int) and 0 <= brightness <= 100 else _DEFAULT_BRIGHTNESS
        self._power = stored.get("power") is not False
        governor = stored.get("governor")
        self._governor = Governor(clock, governor if isinstance(governor, dict) else None)

    # Commands from the UI ------------------------------------------------------------------

    def set_scene(self, scene_id: str, options: dict) -> None:
        if scene_id not in self._scenes:
            raise ValueError(f"unknown scene {scene_id!r}")
        with self._lock:
            self._scene_id, self._options = scene_id, dict(options or {})
            self._rendered_key, self._valid_until, self._pending_user = None, None, True
            self._save()

    def set_brightness(self, percent: int) -> None:
        with self._lock:
            self._brightness = max(0, min(100, int(percent)))
            self._save()

    def set_power(self, on: bool) -> None:
        with self._lock:
            self._power = bool(on)
            self._save()
            if self._link is not None:
                self._request(codec.frame(1, codec.Cmd.POWER, b"\x01" if on else b"\x00"))

    def state(self) -> dict:
        with self._lock:
            pwm = power_guard.pwm_for(self._brightness, self._port.strong_supply) if self._port else None
            return {
                "enabled": self._enabled,
                "present": self._link is not None,
                "port": self._port.dev if self._port else None,
                "bus_port": self._port.bus_port if self._port else None,
                "strong_supply": self._port.strong_supply if self._port else None,
                "busy_by": self._busy_by,
                "scene": self._scene_id,
                "options": dict(self._options),
                "brightness": self._brightness,
                "pwm": pwm,
                "power": self._power,
                "last_upload": self._last_upload,
                "writes": self._governor.stats(),
            }

    def preview(self, scene_id: str, options: dict) -> Segment:
        scene = self._scenes[scene_id]
        ctx = dataclasses.replace(self._context(self._clock()), options=dict(options or {}))
        return scene.render(ctx)

    # Worker ---------------------------------------------------------------------------------

    def tick(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            now = self._clock()
            if self._link is None and not self._connect(now):
                return
            try:
                self._sync_brightness()
                self._sync_scene(now)
            except TransportError as error:
                self._log("WARNING", "upload_failed", error=str(error), scene=self._scene_id)
                self._drop(now)

    def log(self, level: str, message: str, **fields) -> None:
        self._log(level, message, **fields)

    def stop(self) -> None:
        with self._lock:
            if self._link is not None:
                self._link.close()
            self._link = None

    def _connect(self, now: float) -> bool:
        if now < self._next_probe:
            return False
        self._next_probe = now + _RECONNECT_S
        port = self._find_panel()
        if port is None:
            self._port = None
            return False
        holders = self._port_holders(port.dev)
        if holders:
            busy = holders[0][1] or str(holders[0][0])
            if busy != self._busy_by:
                self._log("INFO", "busy", holder=busy, pid=holders[0][0])
            self._busy_by, self._port = busy, port
            return False
        self._busy_by = None
        link = self._open_link(port)
        try:
            link.open()
        except TransportError as error:
            self._log("WARNING", "open_failed", error=str(error))
            return False
        self._port, self._link, self._brightness_sent = port, link, None
        self._rendered_key, self._valid_until = None, None
        self._log("INFO", "connected", port=port.dev, bus_port=port.bus_port, strong=port.strong_supply)
        return True

    def _drop(self, now: float) -> None:
        if self._link is not None:
            self._link.close()
        self._link = None
        self._next_probe = now + _RECONNECT_S
        self._rendered_key, self._valid_until = None, None
        self._log("INFO", "disconnected")

    def _sync_brightness(self) -> None:
        pwm = power_guard.pwm_for(self._brightness, self._port.strong_supply)
        if pwm == self._brightness_sent:
            return
        frame = codec.frame(1, codec.Cmd.BRIGHTNESS, bytes((pwm,)))
        if power_guard.allowed(frame):
            self._link.send(frame)
            self._brightness_sent = pwm

    def _sync_scene(self, now: float) -> None:
        if self._scene_id is None:
            return
        scene = self._scenes[self._scene_id]
        ctx = dataclasses.replace(self._context(now), options=dict(self._options))
        key = (self._scene_id, json.dumps(self._options, sort_keys=True), scene.key(ctx))
        expired = self._valid_until is not None and now >= self._valid_until
        if key == self._rendered_key and not expired:
            return
        segment = scene.render(ctx)
        kind = "user" if self._pending_user else segment.kind
        if segment.firmware_animation is not None:
            self._show_animation(segment.firmware_animation, kind)
        else:
            if not self._upload(segment, kind):
                return
        self._rendered_key, self._valid_until, self._pending_user = key, segment.valid_until, False

    def _show_animation(self, animation: int, kind: str) -> None:
        content = f"firmware:{animation}"
        if self._governor.decide(content, "user") is Decision.DUPLICATE:
            return
        reply = self._request(codec.frame(1, codec.Cmd.ANIMATION, bytes((animation,))))
        ok = reply is not None and codec.is_ack(reply, 1, codec.Cmd.ANIMATION)
        self._governor.record(content, ok=ok, kind=kind)
        self._log("INFO", "animation", animation=animation, ok=ok)

    def _upload(self, segment: Segment, kind: str) -> bool:
        palette, indexed = quantize(segment.frames)
        frames = [gif.Frame(px, delay) for px, delay in zip(indexed, segment.delays_cs)]
        palette = power_guard.limit_palette(palette, frames)
        data = gif.encode(frames, palette)
        content = hashlib.sha1(data).hexdigest()
        decision = self._governor.decide(content, kind, segment.metric)
        if decision is Decision.DUPLICATE:
            return True
        if decision is not Decision.ALLOW:
            self._log("INFO", "skipped", reason=decision.value, scene=self._scene_id)
            return False
        started = time.monotonic()
        ok = self._send_gif(data)
        elapsed = round((time.monotonic() - started) * 1000)
        self._governor.record(content, ok=ok, kind=kind, metric=segment.metric)
        self._save()
        self._last_upload = {"at": self._clock(), "scene": self._scene_id, "bytes": len(data),
                             "frames": len(frames), "ok": ok, "ms": elapsed}
        self._log("INFO" if ok else "WARNING", "upload", **self._last_upload, kind=kind)
        return ok

    def _send_gif(self, data: bytes) -> bool:
        if not power_guard.allowed(codec.frame(1, codec.Cmd.TEST, b"\x00")):
            return False
        self._link.send(codec.frame(1, codec.Cmd.TEST, b"\x00"))
        for frame in codec.gif_upload(data):
            timeout = _END_TIMEOUT_S if frame[3] == codec.Cmd.GIF_END else _ACK_TIMEOUT_S
            reply = self._request(frame, timeout)
            if reply is None or not codec.is_ack(reply, frame[2], frame[3]):
                self._log("WARNING", "nak", command=frame[3], reply=(reply or b"").hex())
                return False
        return True

    def _request(self, frame: bytes, timeout: float = _ACK_TIMEOUT_S) -> bytes | None:
        if not power_guard.allowed(frame):
            self._log("ERROR", "blocked_command", frame=frame.hex())
            return None
        return self._link.request(frame, timeout)

    # Persistence ----------------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            data = json.loads(self._store_path.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        try:
            atomic_json_save(str(self._store_path), {
                "scene": {"id": self._scene_id, "options": self._options},
                "brightness": self._brightness,
                "power": self._power,
                "governor": self._governor.snapshot(),
            })
        except OSError as error:
            self._log("WARNING", "save_failed", error=str(error))


class Worker:
    def __init__(self, svc: PixelService, interval: float = 1.0):
        self._svc, self._interval = svc, interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="jsaux-pixel", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout)
        self._svc.stop()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._svc.tick()
            except Exception as error:  # a scene bug must not kill the worker
                self._svc.log("ERROR", "tick_failed", error=repr(error))
            self._stop.wait(self._interval)
