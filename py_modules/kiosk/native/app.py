"""Native bottom screen: paints the deck on the CPU and flips it straight onto the leased panel.

Runs under the system python, outside Decky, as `python3 app.py <kiosk url> <assets dir>`. Exits with
UNAVAILABLE when this machine has no lease to take or lacks cairo/Pango, so the launcher can fall back.
"""

import heapq
import json
import os
import select
import signal
import sys
import threading
import time

UNAVAILABLE = 3
TOUCHSCREEN = os.environ.get("ARMADA_SECONDARY_TOUCHSCREEN", "bottom_touchscreen")

LIVE_S = 0.5
VITALS_S = 5.0
BATTERY_S = 15.0
SLOW_S = 10.0
CLOCK_S = 10.0
SCALAR_HOLD_S = 1.5
SCALAR_GAP_S = 0.04
FRAME_GAP_S = 1 / 30
PRESS_RELEASE_S = 0.12
SNAPSHOT_PATH = "/tmp/pdc-kiosk-native.png"
FULL = "full"


def _use_bundled_font(assets: str) -> None:
    """Point fontconfig at the bundled Inter before Pango loads; system fonts stay available."""
    cache = os.path.join(os.path.expanduser("~"), ".cache", "panel-de-control", "fontconfig")
    os.makedirs(cache, exist_ok=True)
    conf = os.path.join(cache, "fonts.conf")
    body = (
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
        f"<dir>{assets}</dir><cachedir>{cache}</cachedir></fontconfig>"
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
    """Self-pipe so worker threads can wake the select loop."""

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
    """Polls Panel on a schedule and runs actions in order, off the paint loop."""

    def __init__(self, rpc, wake: Wake):
        super().__init__(daemon=True, name="pdc-kiosk-worker")
        self.rpc = rpc
        self.wake = wake
        self.results: list[tuple[str, object]] = []
        self._lock = threading.Condition()
        self._actions: list[tuple[str, tuple]] = []
        self._scalars: dict[str, float] = {}
        self._schedule: list[tuple[float, str]] = []
        self.scalar_written: dict[str, float] = {}

    def every(self, name: str) -> None:
        heapq.heappush(self._schedule, (0.0, name))

    def act(self, name: str, *args) -> None:
        with self._lock:
            self._actions.append((name, args))
            self._lock.notify()

    def scalar(self, kind: str, value: float) -> None:
        with self._lock:
            self._scalars[kind] = value
            self.scalar_written[kind] = time.monotonic()
            self._lock.notify()

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
                due = self._schedule[0][0] if self._schedule else time.monotonic() + 1
                while not self._actions and not self._scalars and time.monotonic() < due:
                    self._lock.wait(max(0.0, due - time.monotonic()))
                actions, self._actions = self._actions, []
                scalars, self._scalars = self._scalars, {}
            for kind, value in scalars.items():
                self._call(f"{kind}.set", "kiosk_steam", f"{kind}.set", [value])
                time.sleep(SCALAR_GAP_S)
            for name, args in actions:
                self._call(name, name, *args)
            now = time.monotonic()
            while self._schedule and self._schedule[0][0] <= now:
                _, name = heapq.heappop(self._schedule)
                heapq.heappush(self._schedule, (now + self._poll(name), name))

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
        if name == "vitals":
            self._call("vitals", "get_kiosk_vitals")
            return VITALS_S
        if name == "battery":
            self._call("battery", "get_battery_state")
            return BATTERY_S
        if name == "slow":
            for label, method, args in (
                ("cpu", "get_cpu_state", ()),
                ("tdp", "get_tdp_state", ()),
                ("prefs", "get_ui_prefs", ()),
                ("brightness", "kiosk_steam", ("brightness.get", [])),
                ("volume", "kiosk_steam", ("volume.get", [])),
                ("refresh", "kiosk_steam", ("refresh.get", [])),
            ):
                self._call(label, method, *args)
            return SLOW_S
        return SLOW_S


class App:
    def __init__(self, url: str, assets: str):
        from deck import HEIGHT, WIDTH, Deck, Rect, logical_point, rotation_matrix
        from drm import LeasedPanel
        from paint import Icons
        from rpc import PanelRpc
        from touch import Touchscreen, find_device
        import cairo

        self.cairo = cairo
        self.logical_point = logical_point
        with open(os.path.join(assets, "strings.json")) as handle:
            strings = json.load(handle)
        with open(os.path.join(assets, "icons.json")) as handle:
            icons = Icons(json.load(handle))
        self.deck = Deck(strings, icons)
        self.rpc = PanelRpc(url)
        self.panel = LeasedPanel()
        self.matrix = rotation_matrix(self.panel.width, self.panel.height)
        self.surfaces = [
            cairo.ImageSurface.create_for_data(buffer.memory, cairo.FORMAT_RGB24, self.panel.width, self.panel.height, buffer.pitch)
            for buffer in self.panel.buffers
        ]
        # The scene is the deck upright at panel resolution; it is rotated into a buffer on copy.
        self.scale_x, self.scale_y = self.panel.height / WIDTH, self.panel.width / HEIGHT
        self.scene = cairo.ImageSurface(cairo.FORMAT_RGB24, self.panel.height, self.panel.width)
        self.background = cairo.ImageSurface(cairo.FORMAT_RGB24, self.panel.height, self.panel.width)
        self.full = Rect(0, 0, WIDTH, HEIGHT)
        self.background_key: object = None
        self.keys: dict[str, tuple] = {}
        self.pending: list[set[str]] = [set(), set()]
        device = find_device(TOUCHSCREEN)
        self.touch = Touchscreen(device, self.panel.width, self.panel.height) if device else None
        self.wake = Wake()
        self.worker = Worker(self.rpc, self.wake)
        for name in ("live", "vitals", "battery", "slow"):
            self.worker.every(name)
        self.dirty = True
        self.last_frame = 0.0
        self.screen_off = False
        self.press_until = 0.0
        self.snapshot_requested = False
        signal.signal(signal.SIGUSR1, self._request_snapshot)

    def _request_snapshot(self, *_) -> None:
        self.snapshot_requested = True
        self.wake.ring()

    def _write_snapshot(self) -> None:
        """Diagnostics: the deck as the user sees it, upright, at panel resolution."""
        self.scene.write_to_png(SNAPSHOT_PATH)

    def run(self) -> None:
        self.worker.start()
        next_clock = time.monotonic() + CLOCK_S
        watched = [self.wake.read_fd, self.panel.fd] + ([self.touch.fd] if self.touch else [])
        while True:
            now = time.monotonic()
            timeout = max(0.0, min(next_clock - now, (self.last_frame + FRAME_GAP_S - now) if self.dirty else 1.0,
                                   (self.press_until - now) if self.press_until else 1.0))
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
            if self.press_until and now >= self.press_until:
                self.press_until = 0.0
                self.deck.pressed = None
                self.dirty = True
            if now >= next_clock:
                next_clock = now + CLOCK_S
                self.dirty = True
            if self.dirty and not self.screen_off and now - self.last_frame >= FRAME_GAP_S:
                self._paint()

    def _paint(self) -> None:
        """Repaint only regions whose content changed, then copy what this buffer has missed."""
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
        if not changed and not self.pending[self.panel.back_index]:
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
        for pending in self.pending:
            pending.update(changed)

        self.panel.wait_flip(timeout=0.1)
        index = self.panel.back_index
        out = cairo.Context(self.surfaces[index])
        out.set_matrix(self.matrix)
        out.scale(1 / self.scale_x, 1 / self.scale_y)
        for name in self.pending[index]:
            rect = regions[name]
            out.rectangle(rect.x * self.scale_x, rect.y * self.scale_y, rect.w * self.scale_x, rect.h * self.scale_y)
        out.clip()
        out.set_source_surface(self.scene, 0, 0)
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
            return
        if name == "live" and isinstance(value, dict):
            fps = value.get("fps")
            s.history = (s.history + [fps])[-60:] if fps is not None else []
            s.fps, s.playing_s = fps, value.get("playing_s")
            appid = value.get("appid")
            if appid != s.appid:
                s.appid, s.game_name, s.hero, s.logo = appid, None, None, None
                if appid and str(appid).isdigit():
                    self.worker.act("get_kiosk_game", str(appid))
                    threading.Thread(target=self._load_art, args=(str(appid),), daemon=True).start()
        elif name == "get_kiosk_game" and isinstance(value, dict) and value.get("appid") == s.appid:
            s.game_name = value.get("name")
        elif name == "art":
            appid, hero, logo = value
            if appid == s.appid:
                s.hero, s.logo = hero, logo
        elif name in ("vitals", "battery", "cpu", "tdp"):
            setattr(s, name, value)
        elif name == "set_cpu_boost" and isinstance(value, dict):
            s.cpu = value
        elif name == "prefs" and isinstance(value, dict):
            s.lang = value.get("panel-de-control-lang") or s.lang
        elif name in ("brightness", "volume") and isinstance(value, dict) and value.get("ok"):
            written = self.worker.scalar_written.get(name, 0.0)
            if time.monotonic() - written > SCALAR_HOLD_S and self.deck.dragging != ("bri" if name == "brightness" else "vol"):
                setattr(s, name, (value.get("result") or {}).get("value"))
        elif name == "refresh" and isinstance(value, dict) and value.get("ok"):
            s.refresh = value.get("result")
        elif name == "set_kiosk_screen_off" and isinstance(value, dict):
            self.screen_off = bool(value.get("screen_off"))
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
        if self.screen_off:
            if event.kind == "down":
                self.worker.act("set_kiosk_screen_off", False)
            return
        x, y = self.logical_point(event.x, event.y, self.panel.width, self.panel.height)
        deck = self.deck
        if event.kind == "down":
            target = deck.hit(x, y)
            deck.pressed = target
            if target in ("bri", "vol"):
                deck.dragging = target
                self._fader(target, y)
            self.dirty = True
        elif event.kind == "move" and deck.dragging:
            self._fader(deck.dragging, y)
        elif event.kind == "up":
            target = deck.pressed
            if deck.dragging:
                self._fader(deck.dragging, y)
                deck.dragging = None
                deck.pressed = None
            elif target and deck.hit(x, y) == target:
                self._activate(target)
                self.press_until = time.monotonic() + PRESS_RELEASE_S
            else:
                deck.pressed = None
            self.dirty = True

    def _fader(self, name: str, y: float) -> None:
        value = round(self.deck.fader_value(name, y), 3)
        kind = "brightness" if name == "bri" else "volume"
        if getattr(self.deck.state, kind) != value:
            setattr(self.deck.state, kind, value)
            self.worker.scalar(kind, value)
            self.dirty = True

    def _activate(self, name: str) -> None:
        s = self.deck.state
        if name == "turbo":
            boost = (s.cpu or {}).get("boost") or {}
            enabled = not boost.get("enabled")
            s.cpu = {**(s.cpu or {}), "boost": {**boost, "enabled": enabled}}
            game_scope = bool(s.appid) and (s.cpu or {}).get("follows_global") is False
            scope = "game" if game_scope else "global"
            self.worker.act("set_cpu_boost", enabled, scope, s.appid if game_scope else None, s.appid)
        elif name == "shot":
            self.worker.act("kiosk_steam", "screenshot", [])
        elif name == "kbd":
            self.worker.act("kiosk_steam", "keyboard", [])
        elif name == "qam":
            self.worker.act("kiosk_steam", "quick_access", [])
        elif name == "off":
            self.worker.act("set_kiosk_screen_off", True)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return UNAVAILABLE
    url, assets = argv[1], argv[2]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _use_bundled_font(assets)
    try:
        import cairo  # noqa: F401
        import paint  # noqa: F401
        from drm import LeaseError
    except (ImportError, ValueError):
        return UNAVAILABLE
    try:
        app = App(url, assets)
    except (LeaseError, OSError) as error:
        print(f"pdc-kiosk native: {error}", file=sys.stderr)
        return UNAVAILABLE
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
