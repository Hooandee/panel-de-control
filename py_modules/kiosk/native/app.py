import heapq
import json
import os
import select
import signal
import sys
import threading
import time
from xml.sax.saxutils import escape

import lights

UNAVAILABLE = 3
TOUCHSCREEN = os.environ.get("ARMADA_SECONDARY_TOUCHSCREEN", "bottom_touchscreen")

LIVE_S = 0.5
SESSION_S = 5.0
VITALS_S = 5.0
BATTERY_S = 15.0
STEAM_S = 15.0
STATE_S = 30.0
PAUSED_CHECK_S = 5.0
SNAPSHOT_LABELS = {
    "brightness.get": "brightness", "volume.get": "volume", "refresh.get": "refresh",
    "perf.view": "perf", "colores.state": "colores",
}
CLOCK_S = 10.0
SCALAR_HOLD_S = 1.5
SCALAR_GAP_S = 0.04
LIGHTS_GAP_S = 0.15
FRAME_GAP_S = 1 / 30
PRESS_RELEASE_S = 0.12
PICK_CLOSE_S = 0.38
DIALOG_IDLE_S = 20.0
DIALOG_OF_TILE = {"perf": "perf", "fps": "fps", "fan": "fan", "hz": "hz", "rgb": "lights"}
SNAPSHOT_NAME = "pdc-kiosk-native.png"
FULL = "full"


def _use_bundled_font(assets: str) -> None:
    cache = os.path.join(os.path.expanduser("~"), ".cache", "panel-de-control", "fontconfig")
    os.makedirs(cache, exist_ok=True)
    conf = os.path.join(cache, "fonts.conf")
    body = (
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
        f"<dir>{escape(assets)}</dir><cachedir>{escape(cache)}</cachedir></fontconfig>"
    )
    try:
        with open(conf) as handle:
            current = handle.read()
    except OSError:
        current = None
    if current != body:
        with open(conf, "w") as handle:
            handle.write(body)
    os.environ["FONTCONFIG_FILE"] = conf


class Wake:
    def __init__(self):
        self.read_fd, self.write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)

    def ring(self) -> None:
        try:
            os.write(self.write_fd, b"x")
        except BlockingIOError:
            pass

    def drain(self) -> None:
        try:
            while os.read(self.read_fd, 64):
                pass
        except BlockingIOError:
            pass


class Worker(threading.Thread):
    def __init__(self, rpc, wake: Wake):
        super().__init__(daemon=True, name="pdc-kiosk-worker")
        self.rpc = rpc
        self.wake = wake
        self.results: list[tuple[str, object]] = []
        self._lock = threading.Condition()
        self._actions: list[tuple[str, str, tuple]] = []
        self._latest: dict[str, tuple[str, str, tuple]] = {}
        self._gaps: dict[str, float] = {}
        self._next_write: dict[str, float] = {}
        self._schedule: list[tuple[float, str]] = []
        self.written_at: dict[str, float] = {}
        self.paused = False

    def every(self, name: str) -> None:
        heapq.heappush(self._schedule, (0.0, name))

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            if self.paused and not paused:
                self._schedule = [(0.0, name) for _, name in self._schedule]
                heapq.heapify(self._schedule)
            self.paused = paused
            self._lock.notify()

    def act(self, label: str, method: str, *args) -> None:
        with self._lock:
            self._actions.append((label, method, args))
            self._lock.notify()

    def latest(self, slot: str, gap_s: float, label: str, method: str, *args) -> None:
        with self._lock:
            self._latest[slot] = (label, method, args)
            self._gaps[slot] = gap_s
            self.written_at[slot] = time.monotonic()
            self._lock.notify()

    def _due_latest(self, now: float) -> float | None:
        waits = [self._next_write.get(slot, 0.0) for slot in self._latest]
        return min(waits) if waits else None

    def take(self) -> list[tuple[str, object]]:
        with self._lock:
            out, self.results = self.results, []
            return out

    def post(self, name: str, value: object) -> None:
        with self._lock:
            self.results.append((name, value))
        self.wake.ring()

    def run(self) -> None:
        while True:
            with self._lock:
                while True:
                    now = time.monotonic()
                    due = self._schedule[0][0] if self._schedule else now + 1
                    latest_due = self._due_latest(now)
                    if latest_due is not None:
                        due = min(due, latest_due)
                    if self._actions or now >= due:
                        break
                    self._lock.wait(due - now)
                actions, self._actions = self._actions, []
                now = time.monotonic()
                ready = [slot for slot in self._latest if self._next_write.get(slot, 0.0) <= now]
                writes = [self._latest.pop(slot) for slot in ready]
                for slot in ready:
                    self._next_write[slot] = now + self._gaps[slot]
            for label, method, args in writes:
                self._call(label, method, *args)
            for label, method, args in actions:
                self._call(label, method, *args)
            now = time.monotonic()
            while self._schedule and self._schedule[0][0] <= now:
                _, name = heapq.heappop(self._schedule)
                wait = PAUSED_CHECK_S if self.paused else self._poll(name)
                heapq.heappush(self._schedule, (now + wait, name))

    def _call(self, label: str, method: str, *args):
        try:
            result = self.rpc.call(method, *args)
        except Exception as error:  # noqa: BLE001
            self.post(f"error:{label}", str(error))
            return None
        self.post(label, result)
        return result

    def _poll(self, name: str) -> float:
        if name == "live":
            self._call("live", "get_kiosk_live")
            return LIVE_S
        if name == "session":
            self._call("session", "get_kiosk_session")
            return SESSION_S
        if name == "vitals":
            self._call("vitals", "get_kiosk_vitals")
            return VITALS_S
        if name == "battery":
            self._call("battery", "get_battery_state")
            return BATTERY_S
        if name == "steam":
            reply = self._call("snapshot", "kiosk_steam", "snapshot", [])
            if isinstance(reply, dict) and reply.get("ok"):
                for action, value in (reply.get("result") or {}).items():
                    if action in SNAPSHOT_LABELS:
                        self.post(SNAPSHOT_LABELS[action], value)
            return STEAM_S
        if name == "state":
            for label, method in (("cpu", "get_cpu_state"), ("prefs", "get_ui_prefs"), ("fan", "get_fan_curve_state"),
                                  ("bottom_brightness", "get_kiosk_brightness")):
                self._call(label, method)
            return STATE_S
        return STATE_S


class App:
    def __init__(self, url: str, assets: str):
        import dialog
        from deck import FPS_HISTORY, Deck
        from geometry import HEIGHT, WIDTH, Rect, logical_point, rotation
        from drm import LeasedPanel
        from paint import Icons
        from rpc import PanelRpc
        from touch import Touchscreen, find_device
        import cairo

        self.cairo = cairo
        self.dialog = dialog
        self.logical_point = logical_point
        with open(os.path.join(assets, "strings.json")) as handle:
            strings = json.load(handle)
        with open(os.path.join(assets, "icons.json")) as handle:
            icons = Icons(json.load(handle))
        self.deck = Deck(strings, icons)
        self.fps_history = FPS_HISTORY
        self.rpc = PanelRpc(url)
        self.panel = LeasedPanel()
        self.matrix = cairo.Matrix(*rotation(self.panel.width, self.panel.height))
        self.surfaces = [
            cairo.ImageSurface.create_for_data(buffer.memory, cairo.FORMAT_RGB24, self.panel.width, self.panel.height, buffer.pitch)
            for buffer in self.panel.buffers
        ]
        self.scale_x, self.scale_y = self.panel.height / WIDTH, self.panel.width / HEIGHT
        self.scene = cairo.ImageSurface(cairo.FORMAT_RGB24, self.panel.height, self.panel.width)
        self.background = cairo.ImageSurface(cairo.FORMAT_RGB24, self.panel.height, self.panel.width)
        self.screen = cairo.ImageSurface(cairo.FORMAT_RGB24, self.panel.height, self.panel.width)
        self.backdrop = None
        self.overlay_key: tuple | None = None
        self.full = Rect(0, 0, WIDTH, HEIGHT)
        self.background_key: object = None
        self.keys: dict[str, tuple] = {}
        self.pending: list[set[str]] = [set(), set()]
        device = find_device(TOUCHSCREEN)
        self.touch = Touchscreen(device, self.panel.width, self.panel.height) if device else None
        self.wake = Wake()
        self.worker = Worker(self.rpc, self.wake)
        self.frames = self._native_frames()
        for name in ("session" if self.frames else "live", "vitals", "battery", "steam", "state"):
            self.worker.every(name)
        self.dirty = True
        self.last_frame = 0.0
        self.screen_off = False
        self.press_until = 0.0
        self.snapshot_requested = False
        self.last_touch = 0.0
        self.close_at = 0.0
        self.dialog_down: tuple | None = None
        self.bri_toggle = False
        signal.signal(signal.SIGUSR1, self._request_snapshot)

    def _native_frames(self):
        try:
            from focus import FocusedApp
            from gamescope_perf import GamescopePerf
            focus = FocusedApp()
        except (ImportError, OSError):
            return None
        self.focused = focus.read()
        reader = GamescopePerf(app_id=lambda: self.focused, python="")
        reader.start()
        return focus, reader

    def _sample_frames(self) -> None:
        focus, reader = self.frames
        self.focused = focus.read()
        fps = reader.fps()
        s = self.deck.state
        s.history = (s.history + [fps])[-self.fps_history:] if fps is not None else []
        if fps != s.fps or fps is not None:
            s.fps = fps
            self.dirty = True

    def _request_snapshot(self, *_) -> None:
        self.snapshot_requested = True
        self.wake.ring()

    def _write_snapshot(self) -> None:
        folder = os.environ.get("XDG_RUNTIME_DIR")
        if folder:
            (self.screen if self.overlay_key is not None else self.scene).write_to_png(os.path.join(folder, SNAPSHOT_NAME))

    def run(self) -> None:
        self.worker.start()
        next_clock = time.monotonic() + CLOCK_S
        next_frames = time.monotonic()
        watched = [self.wake.read_fd, self.panel.fd] + ([self.touch.fd] if self.touch else [])
        while True:
            now = time.monotonic()
            timeout = max(0.0, min(next_clock - now, (next_frames - now) if self.frames else 1.0,
                                   (self.last_frame + FRAME_GAP_S - now) if self.dirty else 1.0,
                                   (self.press_until - now) if self.press_until else 1.0,
                                   (self.close_at - now) if self.close_at else 1.0))
            readable, _, _ = select.select(watched, [], [], timeout)
            if self.wake.read_fd in readable:
                self.wake.drain()
                for name, value in self.worker.take():
                    self._apply(name, value)
            if self.panel.fd in readable:
                self.panel.drain()
            if self.touch and self.touch.fd in readable:
                for event in self.touch.read():
                    self._touch(event)
            if self.snapshot_requested:
                self.snapshot_requested = False
                self._write_snapshot()
            now = time.monotonic()
            if self.close_at and now >= self.close_at:
                self._close_dialog()
            if self.deck.open_dialog and now - self.last_touch >= DIALOG_IDLE_S:
                self._close_dialog()
            if self.press_until and now >= self.press_until:
                self.press_until = 0.0
                self.deck.pressed = None
                self.dirty = True
            if now >= next_clock:
                next_clock = now + CLOCK_S
                self.dirty = True
            if self.frames and now >= next_frames and not self.screen_off:
                next_frames = now + LIVE_S
                self._sample_frames()
            if self.dirty and not self.screen_off and now - self.last_frame >= FRAME_GAP_S:
                self._paint()

    def _paint(self) -> None:
        cairo, deck = self.cairo, self.deck
        regions = {**deck.regions(), FULL: self.full}
        background_key = deck.background_key()
        changed = set()
        if background_key != self.background_key:
            self.background_key = background_key
            ctx = cairo.Context(self.background)
            ctx.scale(self.scale_x, self.scale_y)
            deck.paint_background(ctx)
            ctx = cairo.Context(self.scene)
            ctx.set_source_surface(self.background, 0, 0)
            ctx.paint()
            self.keys.clear()
            for pending in self.pending:
                pending.add(FULL)
        for name in deck.regions():
            key = deck.key(name)
            if self.keys.get(name) != key:
                self.keys[name] = key
                changed.add(name)
        self.dirty = False
        overlay = deck.dialog_model()
        overlay_key = deck.overlay_key()
        overlay_moved = overlay_key != self.overlay_key
        if not changed and not overlay_moved and not self.pending[self.panel.back_index]:
            return
        scene = cairo.Context(self.scene)
        scene.scale(self.scale_x, self.scale_y)
        for name in changed:
            rect = regions[name]
            scene.save()
            scene.rectangle(rect.x, rect.y, rect.w, rect.h)
            scene.clip()
            scene.save()
            scene.scale(1 / self.scale_x, 1 / self.scale_y)
            scene.set_source_surface(self.background, 0, 0)
            scene.paint()
            scene.restore()
            deck.paint_region(scene, name)
            scene.restore()
        self.scene.flush()
        if overlay_moved and self.overlay_key is None:
            self.backdrop = self.dialog.frosted(self.scene)
        self.overlay_key = overlay_key
        whole = overlay_moved or (overlay is not None and changed)
        for pending in self.pending:
            if whole:
                pending.add(FULL)
            else:
                pending.update(changed)
        source = self.scene
        if overlay is not None:
            ctx = cairo.Context(self.screen)
            ctx.set_source_surface(self.scene, 0, 0)
            ctx.set_operator(cairo.OPERATOR_SOURCE)
            ctx.paint()
            ctx.set_operator(cairo.OPERATOR_OVER)
            ctx.scale(self.scale_x, self.scale_y)
            self.dialog.paint(ctx, overlay, deck.icons, self.backdrop, (self.scale_x, self.scale_y), deck.dialog_drag)
            self.screen.flush()
            source = self.screen

        self.panel.wait_flip(timeout=0.1)
        index = self.panel.back_index
        out = cairo.Context(self.surfaces[index])
        out.set_matrix(self.matrix)
        out.scale(1 / self.scale_x, 1 / self.scale_y)
        for name in self.pending[index]:
            rect = regions[name]
            out.rectangle(rect.x * self.scale_x, rect.y * self.scale_y, rect.w * self.scale_x, rect.h * self.scale_y)
        out.clip()
        out.set_source_surface(source, 0, 0)
        out.get_source().set_filter(cairo.FILTER_NEAREST)
        out.set_operator(cairo.OPERATOR_SOURCE)
        out.paint()
        self.surfaces[index].flush()
        self.pending[index].clear()
        self.panel.present()
        self.last_frame = time.monotonic()

    def _apply(self, name: str, value) -> None:
        s = self.deck.state
        if name.startswith("error:"):
            refetch = {"perf": ("kiosk_steam", "perf.view", []), "fan": ("get_fan_curve_state",), "cpu": ("get_cpu_state",),
                       "colores_write": ("kiosk_steam", "colores.state", []), "colores_install": ("kiosk_steam", "colores.state", [])}
            label = name.split(":", 1)[1]
            if label == "colores_install":
                self.deck.installing = False
            if label in refetch:
                self.worker.act(label.split("_")[0], *refetch[label])
            return
        if name in ("live", "session") and isinstance(value, dict):
            if name == "live":
                fps = value.get("fps")
                s.history = (s.history + [fps])[-self.fps_history:] if fps is not None else []
                s.fps = fps
            s.playing_s = value.get("playing_s")
            appid = value.get("appid")
            if appid != s.appid:
                s.appid, s.game_name, s.hero, s.logo = appid, None, None, None
                if appid and str(appid).isdigit():
                    self.worker.act("get_kiosk_game", "get_kiosk_game", str(appid))
                    threading.Thread(target=self._load_art, args=(str(appid),), daemon=True).start()
        elif name == "get_kiosk_game" and isinstance(value, dict) and value.get("appid") == s.appid:
            s.game_name = value.get("name")
        elif name == "art":
            appid, hero, logo = value
            if appid == s.appid:
                s.hero, s.logo = hero, logo
        elif name in ("vitals", "battery", "cpu", "fan") and isinstance(value, dict):
            setattr(s, name, value)
        elif name == "colores" and isinstance(value, dict) and value.get("ok"):
            s.colores = value.get("result")
        elif name == "colores_install":
            self.deck.installing = False
            self.worker.act("colores", "kiosk_steam", "colores.state", [])
        elif name == "colores_write":
            self.worker.act("colores", "kiosk_steam", "colores.state", [])
        elif name == "perf" and isinstance(value, dict):
            if value.get("ok"):
                s.perf = value.get("result")
            else:
                self.worker.act("perf", "kiosk_steam", "perf.view", [])
        elif name == "prefs" and isinstance(value, dict):
            s.lang = value.get("panel-de-control-lang") or s.lang
        elif name in ("brightness", "volume") and isinstance(value, dict) and value.get("ok"):
            written = self.worker.written_at.get(name, 0.0)
            if time.monotonic() - written > SCALAR_HOLD_S and self.deck.dragging != ("bri" if name == "brightness" else "vol"):
                setattr(s, name, (value.get("result") or {}).get("value"))
        elif name == "bottom_brightness" and isinstance(value, dict):
            written = self.worker.written_at.get("bottom_brightness", 0.0)
            dragging = self.deck.dragging == "bri" and self.deck.bri_target == "bottom"
            if value.get("value") is not None and time.monotonic() - written > SCALAR_HOLD_S and not dragging:
                s.bottom_brightness = value["value"]
        elif name == "refresh" and isinstance(value, dict) and value.get("ok"):
            s.refresh = value.get("result")
        elif name == "screen_off" and isinstance(value, dict):
            self.screen_off = bool(value.get("screen_off"))
            self.worker.set_paused(self.screen_off)
        else:
            return
        self.dirty = True

    def _load_art(self, appid: str) -> None:
        from paint import decode_image

        hero_bytes = self.rpc.fetch(f"/art/{appid}/hero")
        logo_bytes = self.rpc.fetch(f"/art/{appid}/logo")
        hero = decode_image(hero_bytes, 1240) if hero_bytes else None
        logo = decode_image(logo_bytes, 400) if logo_bytes else None
        self.worker.post("art", (appid, hero, logo))

    def _touch(self, event) -> None:
        self.last_touch = time.monotonic()
        if self.screen_off:
            if event.kind == "down":
                self.worker.act("screen_off", "set_kiosk_screen_off", False)
            return
        x, y = self.logical_point(event.x, event.y, self.panel.width, self.panel.height)
        if self.deck.open_dialog:
            self._dialog_touch(event.kind, x, y)
            return
        deck = self.deck
        if event.kind == "down":
            target = deck.hit(x, y)
            deck.pressed = target
            if target == "bri" and deck.in_fader_icon("bri", y) and deck.has_bottom_brightness():
                self.bri_toggle = True
            elif target in ("bri", "vol"):
                deck.dragging = target
                self._fader(target, y)
            self.dirty = True
        elif event.kind == "move" and deck.dragging:
            self._fader(deck.dragging, y)
        elif event.kind == "up":
            target = deck.pressed
            if self.bri_toggle:
                self.bri_toggle = False
                deck.pressed = None
                if deck.hit(x, y) == "bri":
                    deck.toggle_bri_target()
            elif deck.dragging:
                self._fader(deck.dragging, y, final=True)
                deck.dragging = None
                deck.pressed = None
            elif target and deck.hit(x, y) == target:
                self._activate(target)
                self.press_until = time.monotonic() + PRESS_RELEASE_S
            else:
                deck.pressed = None
            self.dirty = True

    def _dialog_touch(self, kind: str, x: float, y: float) -> None:
        deck = self.deck
        model = deck.dialog_model()
        if model is None:
            self._close_dialog()
            return
        if kind == "down":
            hit = self.dialog.hit(model, x, y)
            self.dialog_down = hit
            if hit[0] in ("bar", "steps"):
                deck.dialog_drag = hit
                self._dialog_drag_preview(hit)
                self.dirty = True
        elif kind == "move" and deck.dialog_drag is not None:
            drag_kind, key, _ = deck.dialog_drag
            value = self.dialog.drag_value(model, drag_kind, key, x)
            if value is not None and (drag_kind, key, value) != deck.dialog_drag:
                deck.dialog_drag = (drag_kind, key, value)
                self._dialog_drag_preview(deck.dialog_drag)
                self.dirty = True
        elif kind == "up":
            down, self.dialog_down = self.dialog_down, None
            if deck.dialog_drag is not None:
                drag, deck.dialog_drag = deck.dialog_drag, None
                self._dialog_drag_commit(model, drag)
                self.dirty = True
                return
            hit = self.dialog.hit(model, x, y)
            if down is None or hit[:2] != down[:2]:
                return
            if hit[0] == "outside":
                self._close_dialog()
            elif hit[0] in ("orb", "color", "chip", "cta"):
                self._dialog_pick(hit[0], hit[1])

    def _dialog_drag_preview(self, drag: tuple) -> None:
        kind, key, value = drag
        if kind == "bar":
            change = self._lights_bar_change(key, value)
            if change is not None:
                self.worker.latest("colores", LIGHTS_GAP_S, "colores_preview", "kiosk_steam", "colores.call",
                                   ["patch_profile", [*self._lights_target(), change]])

    def _dialog_drag_commit(self, model, drag: tuple) -> None:
        kind, key, value = drag
        if kind == "steps":
            current = next((section.value for section in model.sections if isinstance(section, self.dialog.Steps)), None)
            if value != current:
                self._perf_optimistic(level=value)
                self.worker.act("perf", "kiosk_steam", "perf.level", [value])
        elif kind == "bar":
            change = self._lights_bar_change(key, value)
            if change is not None:
                self._lights_optimistic(change)
                self.worker.act("colores_write", "kiosk_steam", "colores.call", ["patch_profile", [*self._lights_target(), change]])

    def _lights_state(self) -> dict:
        return (self.deck.state.colores or {}).get("state") or {}

    def _lights_target(self) -> list:
        return list(lights.target(self._lights_state()))

    def _lights_bar_change(self, key: object, fraction: float) -> dict | None:
        state = self._lights_state()
        if not state:
            return None
        if key == "brightness":
            return {"brightness": round(fraction * lights.BRIGHTNESS_MAX)}
        effect = state.get("effect") or {}
        return {"effect": {"id": effect.get("id"), "speed": round(fraction * 100), "use_gradient": bool(effect.get("useGradient"))}}

    def _lights_optimistic(self, change: dict) -> None:
        colores = self.deck.state.colores or {}
        state = dict(colores.get("state") or {})
        for name, value in change.items():
            if name == "effect":
                state["effect"] = {**(state.get("effect") or {}), "id": value["id"], "speed": value["speed"],
                                   "useGradient": value["use_gradient"]}
            elif name == "color":
                state["color"] = {"r": value[0], "g": value[1], "b": value[2]}
            else:
                state[name] = value
        self.deck.state.colores = {**colores, "state": state}
        self.dirty = True

    def _lights_write(self, change: dict) -> None:
        self._lights_optimistic(change)
        self.worker.act("colores_write", "kiosk_steam", "colores.call", ["patch_profile", [*self._lights_target(), change]])

    def _dialog_pick(self, kind: str, key) -> None:
        s = self.deck.state
        if kind == "cta" and key == "install":
            self.deck.installing = True
            self.worker.act("colores_install", "kiosk_steam", "colores.install", [])
            self.dirty = True
            return
        if kind == "color":
            self._lights_write({"color": list(key), "mode": "solid"})
            return
        if kind == "chip":
            effect = self._lights_state().get("effect") or {}
            self._lights_write({"mode": "effect", "effect": {"id": key, "speed": effect.get("speed", 50),
                                                             "use_gradient": bool(effect.get("useGradient"))}})
            return
        action, value = key
        if action == "power":
            self._lights_optimistic({"power": value})
            self.worker.act("colores_write", "kiosk_steam", "colores.call", ["set_power", [value]])
            return
        if action == "mode":
            if not self._lights_state().get("power"):
                self._lights_optimistic({"power": True})
                self.worker.act("colores_write", "kiosk_steam", "colores.call", ["set_power", [True]])
            self._lights_write({"mode": value})
            return
        if action == "preset":
            self._perf_optimistic(preset=value)
            self.worker.act("perf", "kiosk_steam", "perf.preset", [value])
            return
        if action == "fps":
            self.worker.act("perf", "kiosk_steam", "perf.target", [value])
        elif action == "fan":
            game_scope = bool(s.appid) and (s.fan or {}).get("follows_global") is False
            s.fan = {**(s.fan or {}), "preset": value}
            scope, appid = ("game", s.appid) if game_scope else ("global", None)
            if value == "auto":
                self.worker.act("fan", "set_fan_auto", scope, appid)
            else:
                self.worker.act("fan", "set_fan_preset", value, scope, appid)
        elif action == "hz":
            self.worker.act("refresh_set", "kiosk_steam", "refresh.set", [value])
            self.worker.act("refresh", "kiosk_steam", "refresh.get", [])
        self.dirty = True
        self.close_at = time.monotonic() + PICK_CLOSE_S

    def _perf_optimistic(self, level: int | None = None, preset: str | None = None) -> None:
        perf = dict(self.deck.state.perf or {})
        if level is not None:
            perf["shown"] = perf["value"] = level
            perf["presets"] = [{**p, "active": False} for p in perf.get("presets") or []]
        if preset is not None:
            perf["presets"] = [{**p, "active": p["id"] == preset} for p in perf.get("presets") or []]
        self.deck.state.perf = perf
        self.dirty = True

    def _close_dialog(self) -> None:
        self.deck.open_dialog = None
        self.deck.dialog_drag = None
        self.dialog_down = None
        self.close_at = 0.0
        self.dirty = True

    def _screenshot(self) -> None:
        try:
            from gamescope_perf import take_screenshot
            path = time.strftime("/tmp/gamescope_%Y-%m-%d_%H-%M-%S.png")
            if take_screenshot(path):
                return
        except ImportError:
            pass
        self.worker.act("steam", "kiosk_steam", "screenshot", [])

    def _fader(self, name: str, y: float, final: bool = False) -> None:
        value = round(self.deck.fader_value(name, y), 3)
        if name == "bri" and self.deck.bri_target == "bottom":
            if self.deck.state.bottom_brightness != value:
                self.deck.state.bottom_brightness = value
                self.worker.latest("bottom_brightness", SCALAR_GAP_S, "bottom_brightness", "set_kiosk_brightness", value, False)
                self.dirty = True
            if final:
                self.worker.act("bottom_brightness", "set_kiosk_brightness", value, True)
            return
        kind = "brightness" if name == "bri" else "volume"
        if getattr(self.deck.state, kind) != value:
            setattr(self.deck.state, kind, value)
            self.worker.latest(kind, SCALAR_GAP_S, f"{kind}.set", "kiosk_steam", f"{kind}.set", [value])
            self.dirty = True

    def _activate(self, name: str) -> None:
        s = self.deck.state
        if name in DIALOG_OF_TILE:
            self.deck.open_dialog = DIALOG_OF_TILE[name]
            self.dirty = True
        elif name == "turbo":
            boost = (s.cpu or {}).get("boost") or {}
            enabled = not boost.get("enabled")
            s.cpu = {**(s.cpu or {}), "boost": {**boost, "enabled": enabled}}
            game_scope = bool(s.appid) and (s.cpu or {}).get("follows_global") is False
            scope = "game" if game_scope else "global"
            self.worker.act("cpu", "set_cpu_boost", enabled, scope, s.appid if game_scope else None, s.appid)
        elif name == "shot":
            threading.Thread(target=self._screenshot, daemon=True).start()
        elif name == "kbd":
            self.worker.act("steam", "kiosk_steam", "keyboard", [])
        elif name == "qam":
            self.worker.act("steam", "kiosk_steam", "quick_access", [])
        elif name == "off":
            self.worker.act("screen_off", "set_kiosk_screen_off", True)


def _unavailable(reason: object) -> int:
    print(f"pdc-kiosk native: {reason}", file=sys.stderr)
    return UNAVAILABLE


def main(argv: list[str]) -> int:
    url = os.environ.get("PDC_KIOSK_URL")
    if len(argv) < 2 or not url:
        return _unavailable("missing assets folder or PDC_KIOSK_URL")
    assets = argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    sys.path.insert(1, os.path.dirname(os.path.dirname(here)))  # gamescope_perf lives in py_modules
    try:
        _use_bundled_font(assets)
        import cairo  # noqa: F401
        import paint  # noqa: F401
        from drm import LeaseError
    except (ImportError, ValueError, OSError) as error:
        return _unavailable(error)
    try:
        app = App(url, assets)
    except (LeaseError, OSError) as error:
        return _unavailable(error)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
