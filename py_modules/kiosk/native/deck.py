import time
from dataclasses import dataclass, field

import cairo

from choices import fan_choices, fps_choices, level_caption, refresh_choices
import lights
from dialog import Bar, Chips, Colors, Cta, DialogModel, Note, Orb, Orbs, Steps
from geometry import GRID_Y, WIDTH, Rect, grid_rects
from paint import Icons, Text, contain, cover, fill_rounded, glass, rounded_rect, swatch_pattern, white

FPS_HISTORY = 60
DISABLED_ALPHA = 0.45
PRESS_SCALE = 0.95
FADERS = ("bri", "vol")
FADER_ICON_ZONE = 56


@dataclass
class DeckState:
    lang: str = "es"
    fps: float | None = None
    playing_s: int | None = None
    appid: str | None = None
    history: list[float] = field(default_factory=list)
    game_name: str | None = None
    hero: cairo.ImageSurface | None = None
    logo: cairo.ImageSurface | None = None
    vitals: dict | None = None
    battery: dict | None = None
    cpu: dict | None = None
    refresh: dict | None = None
    brightness: float | None = None
    bottom_brightness: float | None = None
    volume: float | None = None
    perf: dict | None = None
    fan: dict | None = None
    colores: dict | None = None


def _number(value: float, digits: int, lang: str) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang in ("es", "it", "de", "pt-BR") else text


def _grouped(value: int, lang: str) -> str:
    text = f"{value:,}"
    return text.replace(",", ".") if lang in ("es", "it", "de", "pt-BR") else text


def format_minutes(minutes: int) -> str:
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d}"


def format_playing(seconds: int | None) -> str | None:
    if seconds is None or seconds < 60:
        return None
    minutes = seconds // 60
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"


class Deck:
    def __init__(self, strings: dict[str, dict[str, str]], icons: Icons):
        self.strings = strings
        self.icons = icons
        self.state = DeckState()
        self.rects = grid_rects()
        self.pressed: str | None = None
        self.dragging: str | None = None
        self.open_dialog: str | None = None
        self.dialog_drag: tuple[str, object, object] | None = None
        self.installing = False
        self.bri_target = "top"

    def t(self, key: str, **params) -> str:
        table = self.strings.get(self.state.lang) or self.strings.get("en") or {}
        text = table.get(key) or (self.strings.get("en") or {}).get(key) or key
        for name, value in params.items():
            text = text.replace("{" + name + "}", str(value))
        return text


    def hit(self, x: float, y: float) -> str | None:
        for name, rect in self.rects.items():
            if rect.contains(x, y) and self.enabled(name):
                return name
        return None

    def enabled(self, name: str) -> bool:
        s = self.state
        if name == "turbo":
            return bool((s.cpu or {}).get("boost", {}).get("supported"))
        if name == "bri":
            return s.brightness is not None or s.bottom_brightness is not None
        if name == "vol":
            return s.volume is not None
        if name == "perf":
            return bool((s.perf or {}).get("ready"))
        if name == "fps":
            return bool((s.perf or {}).get("autoReady"))
        if name == "fan":
            return bool(fan_choices(s.fan))
        if name == "hz":
            return len(refresh_choices(s.refresh)) > 1
        if name == "rgb":
            return (s.colores or {}).get("installed") is not None
        return name in ("shot", "kbd", "qam", "off")

    def bri_value(self) -> float | None:
        return self.state.bottom_brightness if self.bri_target == "bottom" else self.state.brightness

    def has_bottom_brightness(self) -> bool:
        return self.state.bottom_brightness is not None

    def in_fader_icon(self, name: str, y: float) -> bool:
        rect = self.rects[name]
        return y >= rect.y + rect.h - FADER_ICON_ZONE

    def toggle_bri_target(self) -> None:
        if self.bri_target == "top" and self.has_bottom_brightness():
            self.bri_target = "bottom"
        elif self.bri_target == "bottom" and self.state.brightness is not None:
            self.bri_target = "top"
        elif self.state.brightness is None:
            self.bri_target = "bottom"

    def fader_value(self, name: str, y: float) -> float:
        rect = self.rects[name]
        return max(0.0, min(1.0, 1 - (y - rect.y) / rect.h))

    def regions(self) -> dict[str, Rect]:
        return {"head": Rect(0, 0, WIDTH, GRID_Y - 1), **self.rects}

    def background_key(self) -> object:
        return id(self.state.hero)

    def key(self, name: str) -> tuple:
        s = self.state
        if name == "head":
            fps = round(s.fps) if s.fps is not None else None
            celsius = (s.vitals or {}).get("celsius")
            history = tuple(s.history) if len(s.history) >= 2 else ()
            return (s.lang, time.strftime("%H:%M"), self._battery_line(), format_playing(s.playing_s), s.game_name,
                    id(s.logo), fps, self._target(), round(celsius) if celsius is not None else None, history)
        common = (s.lang, name == self.pressed, self.enabled(name))
        vitals = s.vitals or {}
        content = {
            "perf": lambda: (repr(s.perf), vitals.get("cpu_mhz"), vitals.get("gpu_mhz"), vitals.get("watts"), vitals.get("charging"),
                             vitals.get("ram_used_gb")),
            "fan": lambda: (vitals.get("fan_rpm"),),
            "fps": lambda: (self._target(),),
            "rgb": lambda: (repr(s.colores),),
            "hz": lambda: ((s.refresh or {}).get("current"),),
            "turbo": lambda: (bool((s.cpu or {}).get("boost", {}).get("enabled")),),
            "bri": lambda: (s.brightness, s.bottom_brightness, self.bri_target),
            "vol": lambda: (s.volume,),
        }.get(name, tuple)
        return common + content()

    def paint_background(self, ctx: cairo.Context) -> None:
        ctx.set_source_rgb(0, 0, 0)
        ctx.paint()
        if self.state.hero is not None:
            cover(ctx, self.state.hero, 0, 0, WIDTH, 200, focus_y=0.38)
        shade = cairo.LinearGradient(0, -1, 0, 201)
        for stop, alpha in ((0, 0.25), (0.25, 0.05), (0.55, 0.6), (0.88, 1.0), (1, 1.0)):
            shade.add_color_stop_rgba(stop, 0, 0, 0, alpha)
        ctx.rectangle(0, 0, WIDTH, 200)
        ctx.set_source(shade)
        ctx.fill()

    def paint(self, ctx: cairo.Context) -> None:
        self.paint_background(ctx)
        for name in self.regions():
            self.paint_region(ctx, name)

    def paint_region(self, ctx: cairo.Context, name: str) -> None:
        if name == "head":
            self._paint_header(ctx)
            return
        rect = self.rects[name]
        ctx.save()
        if name == self.pressed and name not in FADERS:
            cx, cy = rect.x + rect.w / 2, rect.y + rect.h / 2
            ctx.translate(cx, cy)
            ctx.scale(PRESS_SCALE, PRESS_SCALE)
            ctx.translate(-cx, -cy)
        if not self.enabled(name) and name not in ("perf", "fps", "fan", "hz", "rgb"):
            ctx.push_group()
            self._paint_tile(ctx, name, rect)
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(DISABLED_ALPHA)
        else:
            self._paint_tile(ctx, name, rect)
        ctx.restore()

    def _battery_line(self) -> tuple[str, bool] | None:
        battery = self.state.battery or {}
        if not battery.get("present") or battery.get("percent") is None:
            return None
        status = battery.get("status") or ""
        charging = status == "Charging" or (battery.get("ac_online") is True and status not in ("Full", "Discharging"))
        text = f"{battery['percent']} %"
        if not charging and battery.get("eta_seconds"):
            text += " · " + format_minutes(round(battery["eta_seconds"] / 60))
        return text, charging

    def _paint_header(self, ctx: cairo.Context) -> None:
        s = self.state
        clock = Text(ctx, time.strftime("%H:%M"), 12, 550)
        clock.draw(ctx, 18, 12)
        battery = self._battery_line()
        if battery is not None:
            text, charging = battery
            label = Text(ctx, text, 12, 550)
            label.draw(ctx, WIDTH - 18 - label.width, 12, (0.19, 0.82, 0.35, 1) if charging else white(1))

        bottom = 120.0
        playing = format_playing(s.playing_s)
        if playing:
            session = Text(ctx, self.t("kiosk.header.playing", time=playing), 12, 500)
            session.draw(ctx, 18, bottom - session.height, white(0.75))
            bottom -= session.height + 6
        if s.logo is not None:
            contain(ctx, s.logo, 18, bottom, 200, 58)
        elif s.game_name:
            name = Text(ctx, s.game_name, 24, 650, spacing=-0.03, max_width=330)
            name.draw(ctx, 18, bottom - name.height)

        right = WIDTH - 18.0
        target = self._target()
        if s.fps is not None:
            big = Text(ctx, str(round(s.fps)), 66, 200, spacing=-0.06)
            caption = Text(ctx, self.t("kiosk.header.target", fps=target) if target else "fps", 12, 500)
            column = max(big.width, caption.width)
            big.draw_baseline(ctx, right - big.width, 46 + 66 * 0.85 * 0.8)
            caption.draw(ctx, right - caption.width, 46 + 66 * 0.85)
            right -= column + 22
        celsius = (s.vitals or {}).get("celsius")
        if celsius is not None:
            big = Text(ctx, f"{round(celsius)}°", 36, 250, spacing=-0.04)
            caption = Text(ctx, self.t("kiosk.header.temp"), 12, 500)
            top = 46 + 14
            big.draw_baseline(ctx, right - big.width, top + 36 * 0.85 * 0.8)
            caption.draw(ctx, right - caption.width, top + 36 * 0.85 + 6)

        if len(s.history) >= 2:
            self._paint_pace(ctx, s.history, target)

    def _paint_pace(self, ctx: cairo.Context, samples: list[float], target: int | None) -> None:
        x0, y0, w, h = 18.0, 128.0, WIDTH - 36.0, 22.0
        ceiling = max(target or 0, *samples, 1) * 1.08
        y = lambda v: y0 + h - v / ceiling * h  # noqa: E731
        if target is not None:
            ctx.set_source_rgba(1, 1, 1, 0.18)
            ctx.set_line_width(1)
            ctx.set_dash([2, 3])
            ctx.move_to(x0, y(target))
            ctx.line_to(x0 + w, y(target))
            ctx.stroke()
            ctx.set_dash([])
        step = w / (len(samples) - 1)
        for index, value in enumerate(samples):
            (ctx.move_to if index == 0 else ctx.line_to)(x0 + index * step, y(value))
        ctx.set_source_rgba(1, 1, 1, 0.6)
        ctx.set_line_width(1.3)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke()

    def _target(self) -> int | None:
        return (self.state.perf or {}).get("target")

    def perf_name(self) -> str:
        perf = self.state.perf or {}
        if not perf.get("ready"):
            return self.t("kiosk.unavailable")
        if perf.get("autoOn"):
            return self.t("kiosk.perf.auto")
        active = next((p for p in perf.get("presets") or [] if p.get("active")), None)
        return active["title"] if active else self.t("kiosk.perf.custom")

    def _paint_tile(self, ctx: cairo.Context, name: str, r: Rect) -> None:
        if name in FADERS:
            self._paint_fader(ctx, name, r)
            return
        glass(ctx, r.x, r.y, r.w, r.h)
        painter = getattr(self, f"_tile_{name}", None)
        if painter is not None:
            painter(ctx, r)

    def _small(self, ctx: cairo.Context, r: Rect, icon: str, label: str, on: bool = False) -> None:
        label_text = Text(ctx, label, 11, 550, max_width=r.w - 16)
        block = 34 + 7 + label_text.height
        top = r.y + (r.h - block) / 2
        cx = r.x + r.w / 2
        fill_rounded(ctx, cx - 17, top, 34, 34, 17, (1, 1, 1, 1) if on else white(0.14))
        self.icons.draw(ctx, icon, cx, top + 17, 18, (0.07, 0.07, 0.07, 1) if on else white(1))
        label_text.draw(ctx, cx - label_text.width / 2, top + 41)

    def _big(self, ctx: cairo.Context, r: Rect, value: str, label: str, alpha: float = 1.0) -> None:
        big = Text(ctx, value, 24, 350, spacing=-0.03)
        label_text = Text(ctx, label, 11, 550, max_width=r.w - 16)
        block = big.height + 7 + label_text.height
        top = r.y + (r.h - block) / 2
        big.draw(ctx, r.x + (r.w - big.width) / 2, top, white(alpha))
        label_text.draw(ctx, r.x + (r.w - label_text.width) / 2, top + big.height + 7, white(alpha))

    def _tile_perf(self, ctx: cairo.Context, r: Rect) -> None:
        s = self.state
        perf = s.perf or {}
        value = perf.get("shown")
        high, low = perf.get("max"), perf.get("min") or 0
        x, y = r.x + 16, r.y + 16
        level = Text(ctx, "—" if value is None else str(value), 64, 200, spacing=-0.06)
        level.draw_baseline(ctx, x, y + 64 * 0.85 * 0.82)
        suffix = Text(ctx, f"/ {high}" if perf.get("levels") and high else "W", 14)
        suffix.draw_baseline(ctx, x + level.width + 6, y + 64 * 0.85 * 0.82, white(0.6))
        title = Text(ctx, self.perf_name(), 16, 600, max_width=r.w - 32)
        title.draw(ctx, x, y + 64 * 0.85 + 4, white(1 if perf.get("ready") else DISABLED_ALPHA))

        vitals = s.vitals or {}
        items = []
        if vitals.get("cpu_mhz") is not None:
            items.append(("CPU", _number(vitals["cpu_mhz"] / 1000, 2, s.lang), "GHz"))
        if vitals.get("gpu_mhz") is not None:
            items.append(("GPU", str(vitals["gpu_mhz"]), "MHz"))
        if vitals.get("watts") is not None:
            label = self.t("kiosk.vitals.charging" if vitals.get("charging") else "kiosk.vitals.power")
            items.append((label, _number(vitals["watts"], 1, s.lang), "W"))
        if vitals.get("ram_used_gb") is not None:
            items.append(("RAM", _number(vitals["ram_used_gb"], 1, s.lang), "GB"))
        col_w = (r.w - 32 - 12) / 2
        grid_top = r.y + r.h - 16 - 6 - 14 - 2 * 38
        for index, (label, number, unit) in enumerate(items):
            cx = x + (index % 2) * (col_w + 12)
            cy = grid_top + (index // 2) * 38
            Text(ctx, label, 10.5, 600).draw(ctx, cx, cy, white(0.5))
            value_text = Text(ctx, number, 19, 400, spacing=-0.02)
            value_text.draw(ctx, cx, cy + 13)
            Text(ctx, unit, 11, 500).draw_baseline(ctx, cx + value_text.width + 3, cy + 13 + value_text.baseline, white(0.55))

        span = max(1, (high or 1) - low)
        lit = 0 if value is None else max(1, round((value - low) / span * 10))
        bar_w = (r.w - 32 - 9 * 4) / 10
        for index in range(10):
            fill_rounded(ctx, x + index * (bar_w + 4), r.y + r.h - 16 - 6, bar_w, 6, 3,
                         (1, 1, 1, 1) if index < lit else white(0.16))

    def _tile_fps(self, ctx: cairo.Context, r: Rect) -> None:
        target = self._target()
        label = self.t("kiosk.fps.target") if target is not None else self.t("kiosk.fps.free")
        self._big(ctx, r, "∞" if target is None else str(target), label, 1 if self.enabled("fps") else DISABLED_ALPHA)

    def _tile_fan(self, ctx: cairo.Context, r: Rect) -> None:
        rpm = (self.state.vitals or {}).get("fan_rpm")
        label = self.t("kiosk.fan") if rpm is None else f"{_grouped(rpm, self.state.lang)} rpm" if rpm > 0 else self.t("kiosk.fan.stopped")
        self._small(ctx, r, "fan", label)

    def _tile_hz(self, ctx: cairo.Context, r: Rect) -> None:
        current = (self.state.refresh or {}).get("current")
        self._big(ctx, r, "—" if current is None else str(current), "Hz", 1 if self.enabled("hz") else DISABLED_ALPHA)

    def _tile_rgb(self, ctx: cairo.Context, r: Rect) -> None:
        colores = self.state.colores or {}
        state = colores.get("state")
        if colores.get("installed") is False:
            summary = self.t("kiosk.lights.install")
        elif not state:
            summary = "—"
        elif not state.get("power"):
            summary = self.t("kiosk.lights.off")
        else:
            mode = state.get("mode")
            name = self.t(f"kiosk.lights.effect.{(state.get('effect') or {}).get('id')}") if mode == "effect" \
                else self.t(f"kiosk.lights.mode.{mode}")
            summary = f"{name} · {round((state.get('brightness') or 0) / lights.BRIGHTNESS_MAX * 100)} %"
        alpha = 1 if self.enabled("rgb") else DISABLED_ALPHA
        title = Text(ctx, self.t("kiosk.lights"), 16, 600)
        title.draw(ctx, r.x + 14, r.y + 12, white(alpha))
        sub = Text(ctx, summary, 11, 400, max_width=r.w - 28 - title.width - 8)
        sub.draw_baseline(ctx, r.x + r.w - 14 - sub.width, r.y + 12 + title.baseline, white(0.6 * alpha))
        stops = lights.swatch(state)
        strip_y = r.y + r.h - 12 - 14
        if stops:
            rounded_rect(ctx, r.x + 14, strip_y, r.w - 28, 14, 7)
            ctx.set_source(swatch_pattern(stops, r.x + 14, r.w - 28))
            ctx.fill()
        else:
            fill_rounded(ctx, r.x + 14, strip_y, r.w - 28, 14, 7, white(0.12))

    def _tile_turbo(self, ctx: cairo.Context, r: Rect) -> None:
        on = bool((self.state.cpu or {}).get("boost", {}).get("enabled"))
        self._small(ctx, r, "bolt", self.t("kiosk.turbo"), on)

    def _tile_shot(self, ctx: cairo.Context, r: Rect) -> None:
        self._small(ctx, r, "camera", self.t("kiosk.screenshot"))

    def _tile_kbd(self, ctx: cairo.Context, r: Rect) -> None:
        self._small(ctx, r, "keyboard", self.t("kiosk.keyboard"))

    def _tile_qam(self, ctx: cairo.Context, r: Rect) -> None:
        self._small(ctx, r, "dots", "Steam")

    def _tile_off(self, ctx: cairo.Context, r: Rect) -> None:
        self._small(ctx, r, "screenOff", self.t("kiosk.screenOff"))

    def _paint_fader(self, ctx: cairo.Context, name: str, r: Rect) -> None:
        value = self.bri_value() if name == "bri" else self.state.volume
        fill_rounded(ctx, r.x, r.y, r.w, r.h, 24, white(0.12))
        if value is not None and value > 0:
            ctx.save()
            rounded_rect(ctx, r.x, r.y, r.w, r.h, 24)
            ctx.clip()
            ctx.set_source_rgba(1, 1, 1, 0.95)
            ctx.rectangle(r.x, r.y + r.h * (1 - value), r.w, r.h * value)
            ctx.fill()
            ctx.restore()
        icon = "sun" if name == "bri" else ("muted" if value == 0 else "speaker")
        self.icons.draw(ctx, icon, r.x + r.w / 2, r.y + r.h - 16 - 12, 24, (0x8E / 255, 0x8E / 255, 0x93 / 255, 1), 1.9)
        if name == "bri" and self.has_bottom_brightness() and self.state.brightness is not None:
            label = Text(ctx, self.t(f"kiosk.brightness.{self.bri_target}"), 11, 600, max_width=r.w - 12)
            top = r.y + 12
            under_fill = value is not None and top + label.height > r.y + r.h * (1 - value)
            label.draw(ctx, r.x + (r.w - label.width) / 2, top, (0.11, 0.11, 0.12, 0.8) if under_fill else white(0.7))


    def dialog_model(self) -> DialogModel | None:
        s = self.state
        name = self.open_dialog
        if name == "perf" and s.perf:
            perf = s.perf
            auto = bool(perf.get("autoOn"))
            shown = perf.get("shown")
            caption = level_caption(perf.get("frequencies"), shown, self._comma()) if perf.get("levels") else ""
            detail = self.t("kiosk.perf.autoNote") if auto else (caption or (None if perf.get("levels") else f"{perf.get('value')} W"))
            orbs = tuple(
                Orb(("preset", p["id"]), p["title"], icon=f"preset.{p.get('icon')}", on=bool(p.get("active")), disabled=auto)
                for p in perf.get("presets") or []
            )
            low, high = perf.get("min", 0), perf.get("max", 1)
            sections = ((Orbs(orbs),) if orbs else ()) + (Steps(shown if shown is not None else low, low, high, auto),)
            return DialogModel(self.perf_name(), detail, bubble_text="—" if shown is None else str(shown), sections=sections)
        if name == "fps" and s.perf:
            auto = bool(s.perf.get("autoOn"))
            target = self._target()
            orbs = tuple(Orb(("fps", fps), "fps", text=str(fps), on=auto and target == fps) for fps in fps_choices(s.perf.get("maxFps")))
            orbs += (Orb(("fps", None), self.t("kiosk.fps.free"), icon="infinity", on=not auto),)
            title = "— fps" if s.fps is None else f"{round(s.fps)} fps"
            return DialogModel(title, self.t("kiosk.fps.onNote" if auto else "kiosk.fps.offNote"), bubble_icon="target",
                               sections=(Orbs(orbs),))
        if name == "fan" and s.fan:
            rpm = (s.vitals or {}).get("fan_rpm")
            celsius = (s.vitals or {}).get("celsius")
            orbs = tuple(Orb(("fan", preset), self.t(f"fans.preset.{preset}"), icon=f"fan.{preset}",
                             on=s.fan.get("preset") == preset) for preset in fan_choices(s.fan))
            title = self.t("kiosk.fan") if rpm is None else f"{_grouped(rpm, s.lang)} rpm"
            return DialogModel(title, None if celsius is None else f"{round(celsius)} °C", bubble_icon="fan", sections=(Orbs(orbs),))
        if name == "hz":
            rates = refresh_choices(s.refresh)
            current = (s.refresh or {}).get("current")
            labels = {0: self.t("kiosk.hz.saver"), len(rates) - 1: self.t("kiosk.hz.max")}
            orbs = tuple(Orb(("hz", hz), labels.get(i, "Hz"), text=str(hz), on=current == hz) for i, hz in enumerate(rates))
            return DialogModel(f"{current if current is not None else '—'} Hz", self.t("kiosk.hz.detail"), bubble_icon="display",
                               sections=(Orbs(orbs),))
        if name == "lights":
            return self._lights_model()
        return None

    def _lights_model(self) -> DialogModel | None:
        colores = self.state.colores
        if not colores:
            return None
        if colores.get("installed") is False:
            busy = self.installing
            return DialogModel(self.t("kiosk.lights.installTitle"), self.t("kiosk.lights.installDetail"), bubble_icon="rainbow",
                               sections=(Note(self.t("kiosk.lights.installNote")),
                                         Cta("install", self.t("kiosk.lights.installing" if busy else "kiosk.lights.install"), busy)))
        state = colores.get("state")
        if not state:
            return None
        power = bool(state.get("power"))
        mode = state.get("mode") if power else None
        effect = state.get("effect") or {}
        top = self.t("kiosk.lights.off") if not power else (
            self.t(f"kiosk.lights.effect.{effect.get('id')}") if mode == "effect" else self.t(f"kiosk.lights.mode.{mode}"))
        orbs = (Orb(("power", not power), self.t("kiosk.lights.turnOff"), icon="power", on=not power),)
        orbs += tuple(Orb(("mode", m), self.t(f"kiosk.lights.mode.{m}"), icon=f"light.{m}", on=mode == m)
                      for m in lights.modes(state.get("capabilities")))
        sections: tuple = (Orbs(orbs),)
        if mode == "solid":
            current = lights.rgb(state.get("color"))
            sections += (Colors(tuple((color, color, color == current) for color in lights.SWATCHES)),)
        elif mode == "effect":
            sections += (
                Chips(tuple((e, self.t(f"kiosk.lights.effect.{e}"), e == effect.get("id")) for e in lights.effects(state.get("capabilities")))),
                Bar("speed", (effect.get("speed") or 0) / 100, "speed"),
            )
        elif mode is not None:
            sections += (Note(self.t(f"kiosk.lights.note.{'gradient' if mode == 'gradient' else 'auto'}")),)
        brightness = state.get("brightness") or 0
        sections += (Bar("brightness", brightness / lights.BRIGHTNESS_MAX if power else None, "sun"),)
        return DialogModel(top, self.t("kiosk.lights.detail"), bubble_fill=lights.swatch(state), sections=sections)

    def overlay_key(self) -> tuple | None:
        model = self.dialog_model()
        return None if model is None else (self.open_dialog, model, self.dialog_drag)

    def _comma(self) -> bool:
        return self.state.lang in ("es", "it", "de", "pt-BR")
