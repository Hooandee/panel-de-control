"""Keeps the panel showing the chosen scene with as few flash writes as possible.

`tick()` is one pass: connect when needed, re-render the scene only if its inputs changed or its
segment expired, and upload only what the governor and power guard allow. A worker thread calls
it; it never runs on the asyncio loop.
"""

import copy
import dataclasses
import re
from datetime import datetime, tzinfo
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
from .metrics import Stepper
from .render.canvas import quantize
from .scenes.base import Scene, SceneContext, Segment
from .transport import TransportError, handshake as panel_handshake
from .scenes import words as scene_words

_RECONNECT_S = 5.0
_BUSY_RECHECK_S = 30.0
_NOT_A_PANEL_RECHECK_S = 300.0
_ACK_TIMEOUT_S = 2.0
_FAILURE_BACKOFF_S = (30.0, 120.0, 480.0, 1800.0)
_POWER_BACKOFF_S = (10.0, 30.0, 120.0, 300.0)
_PRESENCE_S = 10.0
_ALERT_STALE_S = 60.0
_NAKS_BEFORE_RECONNECT = 2
_GAME_SETTLE_S = 10.0
# The official daemon waits 20 ms after every command the firmware does not answer; sending the
# next frame sooner can make the panel drop it.
_SETTLE_S = 0.02
_DEFAULT_BRIGHTNESS = 60


_DEFAULT_NIGHT = {"enabled": False, "from": "23:00", "to": "07:00"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def end_timeout(gif_bytes: int) -> float:
    """The closing ack arrives once the GIF is in flash: about 21 ms per KB measured."""
    return 1.0 + 0.03 * gif_bytes / 1024


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _valid_night(night: dict) -> bool:
    return (isinstance(night.get("enabled"), bool) and isinstance(night.get("from"), str)
            and isinstance(night.get("to"), str) and bool(_HHMM.match(night["from"])) and bool(_HHMM.match(night["to"])))


SUSPEND_MODES = ("off", "pet")
_RESUME_JUMP_S = 30.0
_SUSPEND_TIMEOUT_S = 180.0
_IDLE_ANIMATION = 0


class PixelService:
    def __init__(self, *, store_path: Path, find_panel: Callable[[], PanelPort | None],
                 open_link: Callable[[PanelPort], object], port_holders: Callable[[str], list],
                 scenes: dict[str, Scene], context: Callable[[float], SceneContext],
                 log: Callable[..., None], clock: Callable[[], float] = time.time, enabled: bool = True,
                 sleep: Callable[[float], None] = time.sleep,
                 option_extras: Callable[[dict], dict] | None = None,
                 handshake: Callable[[object], bool] = panel_handshake,
                 official_active: Callable[[], bool] = lambda: False,
                 zone: Callable[[], tzinfo | None] = lambda: None):
        self._store_path = Path(store_path)
        self._find_panel, self._open_link, self._port_holders = find_panel, open_link, port_holders
        self._scenes, self._context, self._log, self._clock = scenes, context, log, clock
        self._enabled = enabled
        self._sleep = sleep
        self._option_extras = option_extras or (lambda options: {})
        self._handshake, self._official_active, self._zone = handshake, official_active, zone
        self._held_elsewhere = False
        self._retry_at = 0.0
        self._failures = 0
        self._power_retry_at = 0.0
        self._power_failures = 0
        self._presence_at = 0.0
        self._consecutive_naks = 0
        self._refused: tuple | None = None
        self._playing = False
        self._playing_seen: tuple[bool, float] = (False, 0.0)
        self._seen_key = None
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
        self._power_sent: bool | None = None
        game_scene = stored.get("game_scene")
        self._game_scene: str | None = game_scene if game_scene in scenes else None
        game_options = stored.get("game_options")
        self._game_options: dict = game_options if isinstance(game_options, dict) and self._game_scene else {}
        self._showing: str | None = None
        layout = stored.get("last_layout")
        self._last_layout = layout if isinstance(layout, dict) else (self._options.get("layout") if self._scene_id == "composed" else None)
        self._shown_options: dict = {}
        self._open_error: str | None = None
        self._woke_at = float("-inf")
        self._last_now: float | None = None
        # (scene, data, seconds on screen, requested at); the seconds start once it is written.
        self._alert: tuple[str, dict, float, float] | None = None
        self._alert_until: float | None = None
        self._on_alert = False
        prefs = stored.get("alerts")
        self._alerts = {"achievements": True}
        if isinstance(prefs, dict):
            self._alerts.update({k: bool(v) for k, v in prefs.items() if k in self._alerts})
        self._on_suspend = stored.get("on_suspend") if stored.get("on_suspend") in SUSPEND_MODES else "off"
        self._language = scene_words.language(stored.get("language"))
        self._suspended = False
        self._suspended_at = 0.0
        self._running_appid: str | None = None
        self._chosen_in: str | None = None
        session = stored.get("panel_session")
        self._panel_session: str | None = session if isinstance(session, str) else None
        self._restoring = False
        night = stored.get("night")
        self._night = night if isinstance(night, dict) and _valid_night(night) else dict(_DEFAULT_NIGHT)
        governor = stored.get("governor")
        self._governor = Governor(clock, governor if isinstance(governor, dict) else None)

    # Commands from the UI ------------------------------------------------------------------

    def set_scene(self, scene_id: str, options: dict) -> None:
        if scene_id not in self._scenes:
            raise ValueError(f"unknown scene {scene_id!r}")
        with self._lock:
            self._scene_id, self._options = scene_id, dict(options or {})
            if scene_id == "composed":
                self._last_layout = self._options.get("layout")
            self._chosen_in = self._running_appid
            self._user_changed()
            self._save()

    def _user_changed(self) -> None:
        self._rendered_key, self._valid_until, self._pending_user = None, None, True
        self._retry_at, self._failures, self._refused = 0.0, 0, None

    def refresh(self) -> None:
        """Render again as a user action; identical content is still not rewritten."""
        with self._lock:
            self._user_changed()

    def release_busy(self) -> None:
        with self._lock:
            self._busy_by, self._next_probe = None, 0.0

    def forget_shown(self) -> None:
        with self._lock:
            self._governor.forget_shown()
            self._user_changed()

    def wanted_scenes(self) -> tuple[str | None, str | None, str | None, dict]:
        """Lock-free read for callers on the asyncio loop; plain attribute reads are atomic."""
        return self._scene_id, self._showing, self._game_scene, self._options

    def game_options(self) -> dict:
        return self._game_options

    def set_brightness(self, percent: int) -> None:
        with self._lock:
            self._brightness = max(0, min(100, int(percent)))
            self._save()

    def set_power(self, on: bool) -> None:
        with self._lock:
            self._power = bool(on)
            self._power_retry_at, self._power_failures = 0.0, 0
            self._save()

    def set_game_scene(self, scene_id: str | None, options: dict | None = None) -> None:
        if scene_id is not None and scene_id not in self._scenes:
            raise ValueError(f"unknown scene {scene_id!r}")
        with self._lock:
            self._game_scene = scene_id
            self._chosen_in = None
            self._game_options = dict(options or {}) if scene_id else {}
            self._user_changed()
            self._save()

    def set_alerts(self, prefs: dict) -> None:
        with self._lock:
            self._alerts.update({k: bool(v) for k, v in prefs.items() if k in self._alerts})
            self._save()

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, value: str) -> None:
        """The words the panel shows follow the UI language; a change re-renders the scene once."""
        with self._lock:
            language = scene_words.language(value)
            if language != self._language:
                self._language = language
                self._save()

    def alert_enabled(self, kind: str) -> bool:
        return self._alerts.get(kind, False)

    def show_alert(self, scene_id: str, alert: dict, seconds: float = 20.0) -> None:
        if scene_id not in self._scenes:
            raise ValueError(f"unknown scene {scene_id!r}")
        with self._lock:
            if self._scene_id is None and self._game_scene is None:
                return
            self._alert, self._alert_until = (scene_id, dict(alert), seconds, self._clock()), None
            # The governor spaces alerts itself; a wait left by a live reading would make it stale.
            self._retry_at = 0.0

    def set_on_suspend(self, mode: str) -> None:
        if mode not in SUSPEND_MODES:
            raise ValueError(f"unknown suspend mode {mode!r}")
        with self._lock:
            self._on_suspend = mode
            self._save()

    def suspend(self, asleep: Callable[[], Segment]) -> None:
        """Called just before the Steam Machine sleeps: the panel goes dark or keeps a sleeping pet."""
        requested = self._clock()
        with self._lock:
            # The request can wait on an upload past the sleep itself and win the lock only after
            # the wake: it would then blank a panel that is already awake.
            if self._suspended or requested <= self._woke_at:
                return
            self._suspended, self._suspended_at = True, self._clock()
            self._log("INFO", "suspend", mode=self._on_suspend)
            if self._link is None or (self._scene_id is None and self._game_scene is None):
                return
            now = self._clock()
            try:
                if self._on_suspend == "pet":
                    if not self._power_sent or not self._power or self._night_active(now):
                        return
                    if self._upload(asleep(), "restore", "pet", ("suspend",), now):
                        self._rendered_key = ("suspend",)
                        return
                    # Out of budget: a dark panel beats an alert or a live dashboard left all night.
                    if self._link is None:
                        return
                    reply = self._request(codec.frame(1, codec.Cmd.POWER, b"\x00"))
                    if reply is not None and codec.is_ack(reply, 1, codec.Cmd.POWER):
                        self._power_sent = False
                else:
                    reply = self._request(codec.frame(1, codec.Cmd.POWER, b"\x00"))
                    if reply is not None and codec.is_ack(reply, 1, codec.Cmd.POWER):
                        self._power_sent = False
            except TransportError as error:
                self._log("WARNING", "suspend_failed", error=str(error))
                self._drop(now)

    def resume(self) -> None:
        with self._lock:
            self._woke_at = self._clock()
            if not self._suspended:
                return
            self._suspended = False
            self._rendered_key, self._valid_until, self._retry_at = None, None, 0.0
            self._power_retry_at, self._power_failures = 0.0, 0
            self._restoring = True
            if self._on_suspend == "off":
                # The panel is dark, so a sleep that cut USB power cannot be seen: it would boot
                # into its firmware animation while the stored hash says the scene is still there.
                self._governor.forget_shown()
            self._log("INFO", "resume")

    def set_night(self, night: dict) -> None:
        if not _valid_night(night):
            raise ValueError("invalid night schedule")
        with self._lock:
            self._night = {"enabled": bool(night["enabled"]), "from": night["from"], "to": night["to"]}
            self._save()

    def _night_active(self, now: float) -> bool:
        if not self._night.get("enabled"):
            return False
        minute = _minutes(datetime.fromtimestamp(now, self._zone()).strftime("%H:%M"))
        start, end = _minutes(self._night["from"]), _minutes(self._night["to"])
        if start == end:
            return False
        return start <= minute < end if start < end else minute >= start or minute < end

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
                "game_scene": self._game_scene,
                "game_options": dict(self._game_options),
                "showing": self._showing,
                "shown_options": dict(self._shown_options),
                "last_layout": self._last_layout,
                "refused": self._refused is not None and self._refused[0] == self._scene_id,
                "alerts": dict(self._alerts),
                "brightness": self._brightness,
                "pwm": pwm,
                "power": self._power,
                "night": dict(self._night),
                "on_suspend": self._on_suspend,
                "suspended": self._suspended,
                "night_active": self._night_active(self._clock()),
                "last_upload": self._last_upload,
                "writes": self._governor.stats(),
            }

    def preview(self, scene_id: str, options: dict) -> Segment:
        scene = _detached(self._scenes[scene_id])
        options = dict(options or {})
        ctx = dataclasses.replace(self._context(self._clock()), options={**options, **self._option_extras(options)})
        with self._lock:
            scene.key(ctx)
            return scene.preview(ctx)

    # Worker ---------------------------------------------------------------------------------

    def tick(self) -> None:
        if self._suspended and self._clock() - self._suspended_at >= _SUSPEND_TIMEOUT_S:
            # Steam announced a suspend that never came: the worker kept ticking without a gap.
            self._log("WARNING", "suspend_expired")
            self.resume()
        if not self._enabled or (self._scene_id is None and self._game_scene is None and not self._holds_content()):
            return
        with self._lock:
            now = self._clock()
            if self._last_now is not None and now < self._last_now - _RESUME_JUMP_S:
                # The wall clock went back (NTP): deadlines set before it would hold for that long.
                self._retry_at = self._next_probe = self._power_retry_at = self._presence_at = 0.0
                self._valid_until = None
            self._last_now = now
            if self._link is not None and not self._suspended and not self._still_present(now):
                self._drop(now)
            if self._link is None and (self._suspended or not self._connect(now)):
                return
            base = self._context(now)
            self._track_game(base.game, now)
            if self._suspended:
                return
            try:
                self._sync_brightness()
                self._sync_power(now)
                if self._power_sent:
                    self._sync_scene(now, base)
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
        busy = (holders[0][1] or str(holders[0][0])) if holders else ("jsaux" if self._official_active() else None)
        if busy:
            if busy != self._busy_by:
                self._log("INFO", "busy", holder=busy)
            self._busy_by, self._port, self._held_elsewhere = busy, port, True
            self._next_probe = now + _BUSY_RECHECK_S
            return False
        self._busy_by = None
        link = self._open_link(port)
        try:
            link.open()
        except TransportError as error:
            if str(error) != self._open_error:
                self._log("WARNING", "open_failed", error=str(error))
            self._open_error = str(error)
            self._next_probe = now + _BUSY_RECHECK_S
            return False
        self._open_error = None
        try:
            is_panel = self._handshake(link)
        except TransportError:
            is_panel = False
        if not is_panel:
            link.close()
            self._log("WARNING", "not_a_panel", port=port.dev, bus_port=port.bus_port)
            self._next_probe = now + _NOT_A_PANEL_RECHECK_S
            return False
        self._port, self._link, self._brightness_sent, self._power_sent = port, link, None, None
        self._presence_at = now + _PRESENCE_S
        self._rendered_key, self._valid_until, self._consecutive_naks = None, None, 0
        if self._held_elsewhere or port.session is None or port.session != self._panel_session:
            self._governor.forget_shown()
            self._held_elsewhere = False
            # The panel is back on its firmware animation: putting the scene back is a restore,
            # not a live write that a spent budget or an old failure streak could hold off.
            self._restoring = True
            self._retry_at, self._failures = 0.0, 0
        if port.session != self._panel_session:
            self._panel_session = port.session
            self._save()
        self._log("INFO", "connected", port=port.dev, bus_port=port.bus_port, strong=port.strong_supply)
        return True

    def _still_present(self, now: float) -> bool:
        """A replug while nothing is written goes unnoticed by the open fd, and the panel comes
        back on its firmware animation; the USB session tells it apart."""
        if self._presence_at - _PRESENCE_S <= now < self._presence_at:
            return True
        self._presence_at = now + _PRESENCE_S
        port = self._find_panel()
        if port is not None and self._port is not None and (port.dev, port.session) == (self._port.dev, self._port.session):
            return True
        self._log("INFO", "panel_changed", present=port is not None)
        self._governor.forget_shown()
        return False

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
            self._send_unanswered(frame)
            self._brightness_sent = pwm

    def _sync_power(self, now: float) -> None:
        wanted = self._power and not self._night_active(now)
        if wanted == self._power_sent or now < self._power_retry_at:
            return
        reply = self._request(codec.frame(1, codec.Cmd.POWER, b"\x01" if wanted else b"\x00"))
        if reply is not None and codec.is_ack(reply, 1, codec.Cmd.POWER):
            if wanted and self._power_sent is False:
                self._rendered_key, self._valid_until = None, None
            self._power_sent, self._power_failures, self._power_retry_at = wanted, 0, 0.0
            self._log("INFO", "power", on=wanted, night=self._night_active(now))
        else:
            delay = _POWER_BACKOFF_S[min(self._power_failures, len(_POWER_BACKOFF_S) - 1)]
            self._power_failures += 1
            self._power_retry_at = now + delay
            self._log("WARNING", "power_failed", on=wanted, retry_in_s=delay)

    def _track_game(self, game: dict | None, now: float) -> None:
        """Runs every tick, screen on or off, so a game that ends in the dark is still noticed."""
        appid = str(game.get("appid")) if isinstance(game, dict) and game.get("appid") is not None else None
        self._running_appid = appid
        seen, since = self._playing_seen
        if (appid is not None) != seen:
            self._playing_seen = (appid is not None, now)
        elif now - since >= _GAME_SETTLE_S and self._playing != seen:
            self._playing = seen
            self._restoring = True
            self._log("INFO", "game_started" if seen else "game_ended",
                      game_scene=self._game_scene, chosen_in_game=self._chosen_in is not None)
        # A scene picked during a game wins over the game scene until that game ends.
        if self._chosen_in is not None and (appid != self._chosen_in if appid is not None else not self._playing):
            self._chosen_in = None

    def _sync_scene(self, now: float, base: SceneContext) -> None:
        # A live reading held back must not delay the hour turning over on a clock face.
        expired_face = self._valid_until is not None and now >= self._valid_until
        if now < self._retry_at and not expired_face:
            return
        if self._alert is not None and now >= (self._alert_until if self._alert_until is not None
                                               else self._alert[3] + _ALERT_STALE_S):
            self._alert, self._alert_until = None, None
        playing = self._playing and self._game_scene is not None and self._chosen_in is None
        if self._alert is not None:
            showing, chosen = self._alert[0], {"alert": self._alert[1]}
        else:
            showing = self._game_scene if playing else self._scene_id
            chosen = self._game_options if playing else self._options
            if showing is None:
                # Only a game scene was chosen and the game is over: hand the panel back to the
                # firmware animation it shows on its own rather than freeze the last game frame.
                if self._holds_content() and self._show_animation(_IDLE_ANIMATION, "restore", now):
                    self._showing, self._shown_options, self._rendered_key = None, {}, None
                return
        scene = self._scenes[showing]
        options = {**chosen, **self._option_extras(chosen)}
        ctx = dataclasses.replace(base, options=options)
        key = (showing, json.dumps(options, sort_keys=True), scene.key(ctx))
        expired = self._valid_until is not None and now >= self._valid_until
        if key == self._rendered_key and not expired:
            self._alert_shown(now)
            return
        if self._refused is not None and self._refused == key:
            return
        if scene.SETTLE and key != self._seen_key:
            # Live readings settle a tick later (CPU load needs two samples); waiting one tick
            # avoids writing a placeholder that is replaced a second later.
            self._seen_key = key
            return
        segment = scene.render(ctx)
        if not segment.ready:
            return
        if self._pending_user:
            kind = "user"
        elif self._alert is not None:
            kind = "alert"
        elif self._restoring or self._on_alert:
            kind = "restore"
        elif expired and key[:2] == (self._rendered_key or (None, None))[:2]:
            kind = "boundary"
        else:
            kind = segment.kind
        if segment.firmware_animation is not None:
            if not self._show_animation(segment.firmware_animation, kind, now):
                return
        elif not self._upload(segment, kind, showing, key, now):
            return
        self._rendered_key, self._valid_until, self._pending_user = key, segment.valid_until, False
        self._showing, self._restoring, self._on_alert = showing, False, self._alert is not None
        self._shown_options = dict(chosen)
        self._alert_shown(now)

    def _holds_content(self) -> bool:
        """Something of ours is on the panel (a game frame, the sleeping pet), not its own animation."""
        return self._governor.last_shown not in (None, f"firmware:{_IDLE_ANIMATION}")

    def _alert_shown(self, now: float) -> None:
        if self._alert is not None and self._alert_until is None:
            self._alert_until = now + self._alert[2]

    def _back_off(self, now: float) -> None:
        delay = _FAILURE_BACKOFF_S[min(self._failures, len(_FAILURE_BACKOFF_S) - 1)]
        self._failures += 1
        self._retry_at = now + delay
        self._log("WARNING", "upload_failed_backoff", retry_in_s=delay, failures=self._failures)

    def _show_animation(self, animation: int, kind: str, now: float) -> bool:
        content = f"firmware:{animation}"
        if self._governor.decide(content, "user") is Decision.DUPLICATE:
            return True
        reply = self._request(codec.frame(1, codec.Cmd.ANIMATION, bytes((animation,))))
        ok = reply is not None and codec.is_ack(reply, 1, codec.Cmd.ANIMATION)
        self._governor.record(content, ok=ok, kind=kind)
        self._log("INFO" if ok else "WARNING", "animation", animation=animation, ok=ok)
        if not ok:
            self._back_off(now)
        return ok

    def _upload(self, segment: Segment, kind: str, scene_id: str, key: tuple, now: float) -> bool:
        palette, indexed = quantize(segment.frames)
        frames = [gif.Frame(px, delay) for px, delay in zip(indexed, segment.delays_cs)]
        palette = power_guard.limit_palette(palette, frames)
        data = gif.encode(frames, palette, loop=True)
        if len(data) > codec.MAX_GIF_BYTES:
            self._refused = key
            self._log("WARNING", "too_large", scene=scene_id, bytes=len(data))
            return False
        content = hashlib.sha1(data).hexdigest()
        decision = self._governor.decide(content, kind, segment.metric)
        if decision is Decision.DUPLICATE:
            return True
        if decision is not Decision.ALLOW:
            self._log("INFO", "skipped", reason=decision.value, scene=scene_id)
            if kind == "alert" and decision is Decision.BUDGET and self._alert is not None:
                # An alert out of budget is dropped, so the scene goes back without waiting.
                self._alert, self._alert_until = None, None
                return False
            self._retry_at = now + self._governor.retry_in(kind, segment.metric, decision)
            return False
        started = time.monotonic()
        ok = self._send_gif(data)
        elapsed = round((time.monotonic() - started) * 1000)
        self._governor.record(content, ok=ok, kind=kind, metric=segment.metric)
        self._save()
        self._last_upload = {"at": self._clock(), "scene": scene_id, "bytes": len(data),
                             "frames": len(frames), "ok": ok, "ms": elapsed}
        self._log("INFO" if ok else "WARNING", "upload", **self._last_upload, kind=kind)
        if ok:
            self._failures, self._consecutive_naks = 0, 0
            return True
        self._consecutive_naks += 1
        self._back_off(now)
        if self._consecutive_naks >= _NAKS_BEFORE_RECONNECT:
            self._consecutive_naks = 0
            self._drop(now)
        return False

    def _send_gif(self, data: bytes) -> bool:
        if not power_guard.allowed(codec.frame(1, codec.Cmd.TEST, b"\x00")):
            return False
        self._send_unanswered(codec.frame(1, codec.Cmd.TEST, b"\x00"))
        for frame in codec.gif_upload(data):
            timeout = end_timeout(len(data)) if frame[3] == codec.Cmd.GIF_END else _ACK_TIMEOUT_S
            reply = self._request(frame, timeout)
            if reply is None or not codec.is_ack(reply, frame[2], frame[3]):
                self._log("WARNING", "nak", command=frame[3], reply=(reply or b"").hex(),
                          frame=frame[:24].hex(), gif_bytes=len(data), gif_head=data[:64].hex())
                return False
        return True

    def _send_unanswered(self, frame: bytes) -> None:
        self._link.send(frame)
        self._sleep(_SETTLE_S)

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
                "night": self._night,
                "game_scene": self._game_scene,
                "game_options": self._game_options,
                "alerts": self._alerts,
                "on_suspend": self._on_suspend,
                "language": self._language,
                "panel_session": self._panel_session,
                "last_layout": self._last_layout,
                "governor": self._governor.snapshot(),
            })
        except OSError as error:
            self._log("WARNING", "save_failed", error=str(error))


def _detached(scene: Scene) -> Scene:
    """A copy whose hysteresis state can move without touching the scene the worker uploads."""
    twin = copy.copy(scene)
    for name, value in vars(scene).items():
        if isinstance(value, (Stepper, dict)):
            setattr(twin, name, copy.deepcopy(value))
    return twin


class Worker:
    def __init__(self, svc: PixelService, interval: float = 1.0, wall: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        self._svc, self._interval = svc, interval
        self._wall, self._monotonic = wall, monotonic
        self._last: tuple[float, float] | None = None
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

    def step(self) -> None:
        wall, mono = self._wall(), self._monotonic()
        if self._last is not None and (wall - self._last[0]) - (mono - self._last[1]) > _RESUME_JUMP_S:
            # The monotonic clock stops while the machine sleeps; the wall clock does not.
            self._svc.resume()
        self._last = (wall, mono)
        self._svc.tick()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception as error:  # a scene bug must not kill the worker
                self._svc.log("ERROR", "tick_failed", error=repr(error))
            self._stop.wait(self._interval)
