"""Weather for the panel from Open-Meteo, for a city the user picks (no IP geolocation)."""

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

from http_util import ssl_context

from . import codec
from .metrics import Stepper
from .render import fonts
from .render.canvas import Canvas
from .render.palettes import mix, scale
from .scenes.base import Scene, SceneContext, Segment

W, H = codec.WIDTH, codec.HEIGHT
_TTL_S = 30 * 60
_RETRY_S = 5 * 60
_RETRY_MAX_S = 30 * 60
_TIMEOUT_S = 6
_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?"
_FORECAST = "https://api.open-meteo.com/v1/forecast?"

SAMPLE_CODES = {"clear": 0, "cloud": 2, "fog": 45, "rain": 63, "snow": 75, "storm": 95}


def _http_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "PanelDeControl"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_S, context=ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def search_cities(query: str, language: str = "es", fetch: Callable[[str], dict] = _http_json) -> list[dict]:
    params = urllib.parse.urlencode({"name": query.strip(), "count": 6, "language": language, "format": "json"})
    try:
        results = fetch(_GEOCODE + params).get("results") or []
    except (OSError, ValueError):
        return []
    cities = []
    for item in results:
        try:
            detail = ", ".join(part for part in (item.get("admin1"), item.get("country")) if part)
            cities.append({"name": str(item["name"]), "detail": detail,
                           "lat": float(item["latitude"]), "lon": float(item["longitude"])})
        except (KeyError, TypeError, ValueError):
            continue
    return cities


def group_for(code: int) -> str:
    if code in (0, 1):
        return "clear"
    if code in (2, 3):
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "rain"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="pdc-weather", daemon=True).start()


class WeatherSource:
    """Cached forecasts. Callers never wait on the network: a stale entry triggers a background
    refresh, and failures back off from 5 to 30 minutes."""

    def __init__(self, fetch: Callable[[str], dict] = _http_json, clock: Callable[[], float] = time.time,
                 spawn: Callable[[Callable[[], None]], None] = _spawn):
        self._fetch, self._clock, self._spawn = fetch, clock, spawn
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._next_try: dict[tuple, float] = {}
        self._failures: dict[tuple, int] = {}
        self._busy: set[tuple] = set()
        self._lock = threading.Lock()

    def current(self, city: dict) -> dict | None:
        key = (round(float(city["lat"]), 2), round(float(city["lon"]), 2))
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            fresh = cached is not None and now - cached[0] < _TTL_S
            due = now >= self._next_try.get(key, 0.0) and key not in self._busy
            if not fresh and due:
                self._busy.add(key)
                start = True
            else:
                start = False
        if start:
            self._spawn(lambda: self._refresh(key))
            with self._lock:
                cached = self._cache.get(key)
        return cached[1] if cached else None

    def pending(self, city: dict) -> bool:
        key = (round(float(city["lat"]), 2), round(float(city["lon"]), 2))
        with self._lock:
            return key not in self._cache and (key in self._busy or key not in self._next_try)

    def _refresh(self, key: tuple) -> None:
        params = urllib.parse.urlencode({
            "latitude": key[0], "longitude": key[1], "timezone": "auto", "forecast_days": 1,
            "current": "temperature_2m,weather_code,is_day",
            "daily": "temperature_2m_max,temperature_2m_min",
        })
        try:
            data = self._fetch(_FORECAST + params)
            current, daily = data["current"], data["daily"]
            reading = {
                "temp": float(current["temperature_2m"]),
                "code": int(current["weather_code"]),
                "day": bool(current["is_day"]),
                "high": float(daily["temperature_2m_max"][0]),
                "low": float(daily["temperature_2m_min"][0]),
            }
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            with self._lock:
                failures = self._failures.get(key, 0)
                self._failures[key] = failures + 1
                self._next_try[key] = self._clock() + min(_RETRY_MAX_S, _RETRY_S * 2 ** failures)
                self._busy.discard(key)
            return
        with self._lock:
            self._cache[key] = (self._clock(), reading)
            self._failures.pop(key, None)
            self._next_try.pop(key, None)
            self._busy.discard(key)


def _city(options: dict) -> dict | None:
    city = options.get("city")
    if isinstance(city, dict) and isinstance(city.get("lat"), (int, float)) and isinstance(city.get("lon"), (int, float)):
        return city
    return None


class WeatherScene(Scene):
    id = "weather"
    UPLOADS_PER_HOUR = 3
    OPTIONS = ("city",)

    def __init__(self, source: WeatherSource | None):
        self._source = source
        self._temp = Stepper(1, 0.4)
        self._reading: dict | None = None

    def key(self, ctx: SceneContext):
        city = _city(ctx.options)
        reading = self._source.current(city) if city and self._source else None
        self._reading = reading
        if reading is None:
            return city and city.get("name"), None
        return (city.get("name"), group_for(reading["code"]), reading["day"], self._temp(reading["temp"]),
                round(reading["high"]), round(reading["low"]))

    def render(self, ctx: SceneContext) -> Segment:
        if self._reading is None:
            canvas = Canvas()
            city = _city(ctx.options)
            if city:
                _degrees(canvas, "--", 16)
            else:
                _pin(canvas)
            waiting = bool(city) and self._source is not None and self._source.pending(city)
            return Segment([canvas], [100], ready=not waiting)
        reading = dict(self._reading, temp=self._temp.shown if self._temp.shown is not None else self._reading["temp"])
        return self.render_reading(reading, ctx.options)

    def render_reading(self, reading: dict, options: dict) -> Segment:
        group, day = group_for(reading["code"]), reading["day"]
        count = 24
        frames = [self._frame(group, day, i / count, reading, options) for i in range(count)]
        return Segment(frames, [8] * count)

    def _frame(self, group: str, day: bool, t: float, reading: dict, options: dict) -> Canvas:
        canvas = Canvas()
        _ICONS[group if day or group not in ("clear",) else "night"](canvas, t)
        _degrees(canvas, str(round(reading["temp"])), 6)
        hi_lo = f"{round(reading['high'])} / {round(reading['low'])}"
        canvas.text(W - 2 - fonts.measure(hi_lo, fonts.TINY), 24, hi_lo, fonts.TINY, (150, 160, 210))
        city = (_city(options) or {}).get("name", "").upper()
        if fonts.measure(city, fonts.SMALL) > W - 4:
            city = city[: max(1, (W - 4) // 6)]
        canvas.rect(4, 38, W - 8, 1, (40, 36, 60))
        canvas.text((W - fonts.measure(city, fonts.SMALL)) // 2, 43, city, fonts.SMALL, (190, 180, 240))
        return canvas


def _degrees(canvas: Canvas, number: str, y: int) -> None:
    font = fonts.big(14)
    x = W - 7 - fonts.measure(number, font)
    canvas.text(x, y, number, font, (255, 255, 255))
    canvas.text(W - 5, y, "°", fonts.TINY, (200, 200, 230))


def _pin(canvas: Canvas) -> None:
    cx, cy = W // 2, 20
    canvas.circle(cx, cy, 8, (170, 110, 255), filled=True)
    canvas.circle(cx, cy, 3, (0, 0, 0), filled=True)
    for dy in range(1, 11):
        half = max(0, 7 - dy)
        canvas.rect(cx - half, cy + 6 + dy, half * 2 + 1, 1, (120, 160, 255))


_SUN = (255, 200, 60)
_CLOUD = (200, 210, 235)


def _sun(canvas: Canvas, t: float, cx: int = 15, cy: int = 16) -> None:
    canvas.circle(cx, cy, 6, _SUN, filled=True)
    canvas.circle(cx - 2, cy - 2, 2, (255, 235, 150), filled=True)
    for ray in range(8):
        angle = math.tau * (ray / 8 + t / 8)
        reach = 11 + round(math.sin(math.tau * (t * 2 + ray / 8)) * 2)
        for r in range(8, reach + 1):
            canvas.px(round(cx + r * math.cos(angle)), round(cy + r * math.sin(angle)), scale(_SUN, 1.1 - (r - 8) * 0.15))


def _night(canvas: Canvas, t: float) -> None:
    canvas.circle(15, 16, 7, (230, 225, 200), filled=True)
    canvas.circle(18, 13, 6, (0, 0, 0), filled=True)
    for k, (x, y) in enumerate(((4, 5), (27, 8), (24, 26), (6, 27), (30, 18))):
        glow = 0.5 + 0.5 * math.sin(math.tau * (t + k / 5))
        canvas.px(x, y, scale((220, 220, 255), 0.25 + 0.75 * glow))


def _cloud(canvas: Canvas, x: int, y: int, colour=_CLOUD) -> None:
    canvas.circle(x + 6, y + 6, 5, colour, filled=True)
    canvas.circle(x + 13, y + 4, 6, colour, filled=True)
    canvas.circle(x + 19, y + 7, 4, colour, filled=True)
    canvas.rect(x + 3, y + 7, 19, 5, colour)


def _clouds(canvas: Canvas, t: float) -> None:
    _sun(canvas, t, 21, 10)
    shift = round(math.sin(math.tau * t) * 5)
    _cloud(canvas, 2 + shift, 12)
    small = round(((t + 0.5) % 1.0) * 40) - 8
    canvas.circle(small + 3, 4, 2, (170, 180, 210), filled=True)
    canvas.rect(small + 1, 5, 7, 2, (170, 180, 210))


def _fog(canvas: Canvas, t: float) -> None:
    for row in range(5):
        offset = round((t * 2 + row * 0.37) % 1.0 * 8)
        for x in range(2, 30):
            if (x + offset) % 8 < 6:
                canvas.px(x, 8 + row * 4, mix((120, 130, 160), _CLOUD, row / 4))


def _falling(canvas: Canvas, t: float, colour, count: int, speed: int, wiggle: float) -> None:
    for k in range(count):
        x0 = 4 + (k * 7) % 25
        phase = (t * speed + k / count) % 1.0
        y = 18 + round(phase * 14)
        x = x0 + round(math.sin(math.tau * (phase + k / count)) * wiggle)
        canvas.px(x, y, colour)
        if wiggle == 0:
            canvas.px(x, y - 1, scale(colour, 0.5))


def _rain(canvas: Canvas, t: float) -> None:
    _falling(canvas, t, (90, 170, 255), 12, 3, 0)
    _cloud(canvas, 3, 4, (150, 160, 190))


def _snow(canvas: Canvas, t: float) -> None:
    _falling(canvas, t, (240, 245, 255), 11, 1, 1.6)
    _cloud(canvas, 3, 4, (190, 200, 225))


def _storm(canvas: Canvas, t: float) -> None:
    _falling(canvas, t, (90, 170, 255), 10, 3, 0)
    flash = 0.5 <= t < 0.6
    _cloud(canvas, 3, 4, (200, 200, 230) if flash else (110, 110, 140))
    if flash:
        for x, y in ((15, 14), (14, 16), (13, 18), (15, 18), (14, 20), (13, 22), (12, 24)):
            canvas.px(x, y, (255, 240, 120))


_ICONS = {"clear": _sun, "night": _night, "cloud": _clouds, "fog": _fog, "rain": _rain, "snow": _snow, "storm": _storm}
