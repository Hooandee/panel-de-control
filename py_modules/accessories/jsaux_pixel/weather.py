"""Weather for the panel from Open-Meteo, for a city the user picks (no IP geolocation)."""

import http.client
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
from .render.text import fit, plain_text
from .scenes.base import Scene, SceneContext, Segment

W, H = codec.WIDTH, codec.HEIGHT
_TTL_S = 30 * 60
# Older than this a reading is shown as unknown: yesterday's temperature or a sun at night would lie.
_STALE_S = 3 * 3600
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
    except (OSError, ValueError, http.client.HTTPException):
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
        return cached[1] if cached and now - cached[0] < _STALE_S else None

    def pending(self, city: dict) -> bool:
        key = (round(float(city["lat"]), 2), round(float(city["lon"]), 2))
        with self._lock:
            # A refresh under way also covers a reading gone stale (a long sleep): wait for it
            # rather than write "--" and the new reading a second later.
            if key in self._busy:
                return True
            if key not in self._cache:
                return key not in self._next_try
            # A stale reading after a long sleep: the first fetch often runs before the network is
            # back, so give it one retry before writing "--".
            return self._clock() - self._cache[key][0] >= _STALE_S and self._failures.get(key, 0) < 2

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
        except Exception:  # noqa: BLE001 - http.client errors are not OSError; a dead thread would pin _busy
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
    OPTIONS = ("city", "style")

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
        if options.get("style") == "sky":
            return _sky_frame(group, day, t, reading, options)
        canvas = Canvas()
        _ICONS[group if day or group not in ("clear",) else "night"](canvas, t)
        _degrees(canvas, str(round(reading["temp"])), 6)
        hi_lo = f"{round(reading['high'])} / {round(reading['low'])}"
        canvas.text(W - 2 - fonts.measure(hi_lo, fonts.TINY), 24, hi_lo, fonts.TINY, (150, 160, 210))
        city = fit(plain_text((_city(options) or {}).get("name", "")), fonts.SMALL, W - 4)
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


# Full-sky style: the whole display is the weather, with the reading on top -------------------

_SKIES = {
    ("clear", True): ((40, 90, 190), (110, 170, 240)),
    ("clear", False): ((4, 8, 30), (20, 26, 70)),
    ("cloud", True): ((70, 90, 130), (130, 145, 175)),
    ("cloud", False): ((12, 16, 34), (34, 40, 66)),
    ("fog", True): ((90, 96, 110), (140, 146, 158)),
    ("fog", False): ((24, 26, 34), (52, 56, 66)),
    ("rain", True): ((40, 48, 70), (80, 90, 112)),
    ("rain", False): ((10, 12, 24), (30, 34, 52)),
    ("snow", True): ((90, 110, 150), (170, 185, 210)),
    ("snow", False): ((16, 20, 40), (46, 54, 84)),
    ("storm", True): ((18, 18, 34), (46, 44, 70)),
    ("storm", False): ((6, 6, 16), (26, 24, 44)),
}


_BOLT = ((44, 12), (39, 20), (43, 20), (37, 30))


def _sky_frame(group: str, day: bool, t: float, reading: dict, options: dict) -> Canvas:
    canvas = Canvas()
    top, bottom = _SKIES[(group, day)]
    flash = group == "storm" and (0.5 <= t < 0.56 or 0.62 <= t < 0.66)
    for y in range(H):
        colour = mix(top, bottom, y / (H - 1))
        canvas.rect(0, y, W, 1, mix(colour, (200, 200, 230), 0.55) if flash else colour)
    if group == "clear" and day:
        _sun(canvas, t, 50, 11)
        _puff(canvas, round(((t + 0.2) % 1.0) * (W + 24)) - 12, 22, (235, 240, 255))
    elif group == "clear":
        canvas.circle(50, 11, 6, (235, 230, 205), filled=True)
        canvas.circle(53, 8, 5, top, filled=True)
        for k, (x, y) in enumerate(((6, 4), (18, 9), (30, 3), (40, 18), (8, 20), (26, 24), (58, 26), (36, 10))):
            glow = 0.5 + 0.5 * math.sin(math.tau * (t + k / 8))
            canvas.px(x, y, scale((230, 230, 255), 0.3 + 0.7 * glow))
    else:
        cloud = {"cloud": (200, 206, 222), "fog": (170, 174, 184), "rain": (120, 126, 146), "snow": (210, 216, 232),
                 "storm": (78, 76, 98)}[group]
        if not day:
            cloud = scale(cloud, 0.45)
        for layer, (y, speed, size) in enumerate(((3, 1, 1.0), (12, 2, 0.8), (-2, 1, 1.2))):
            x = round(((t * speed + layer / 3) % 1.0) * (W + 30)) - 15
            _puff(canvas, x, y, mix(cloud, (255, 255, 255), 0.15 * layer) if layer != 2 else scale(cloud, 0.85))
            _puff(canvas, x - W - 30, y, cloud)
        if group in ("rain", "storm"):
            for k in range(22):
                phase = (t * 3 + k / 22) % 1.0
                x = (k * 13 + round(phase * 6)) % W
                y = round(phase * (H + 6)) - 4
                canvas.line(x, y, x - 1, y + 3, (110, 170, 240) if day else (70, 110, 170))
        if group == "snow":
            for k in range(26):
                phase = (t + k / 26) % 1.0
                x = (k * 17 + round(math.sin(math.tau * (phase + k / 5)) * 2)) % W
                canvas.px(x, round(phase * (H + 2)) - 1, (245, 248, 255))
        if group == "fog":
            for row in range(4):
                offset = round(((t + row * 0.3) % 1.0) * 16)
                for x in range(W):
                    if (x + offset) % 16 < 11:
                        canvas.px(x, 26 + row * 6, mix(top, (230, 232, 236), 0.45))
        if flash:
            for (x0, y0), (x1, y1) in zip(_BOLT, _BOLT[1:]):
                canvas.line(x0, y0, x1, y1, (255, 245, 150))
                canvas.line(x0 + 1, y0, x1 + 1, y1, (255, 220, 90))
    _shadowed(canvas, 3, 31, str(round(reading["temp"])), fonts.big(14), (255, 255, 255))
    degree_x = 3 + fonts.measure(str(round(reading["temp"])), fonts.big(14)) + 1
    _shadowed(canvas, degree_x, 31, "°", fonts.TINY, (255, 255, 255))
    hi_lo = f"{round(reading['high'])}/{round(reading['low'])}"
    _shadowed(canvas, W - 2 - fonts.measure(hi_lo, fonts.TINY), 47, hi_lo, fonts.TINY, (230, 235, 255))
    city = fit(plain_text((_city(options) or {}).get("name", "")), fonts.TINY, W - 6)
    _shadowed(canvas, W - 2 - fonts.measure(city, fonts.TINY), 39, city, fonts.TINY, (230, 235, 255))
    return canvas


def _puff(canvas: Canvas, x: int, y: int, colour) -> None:
    canvas.circle(x + 5, y + 5, 4, colour, filled=True)
    canvas.circle(x + 11, y + 3, 5, colour, filled=True)
    canvas.circle(x + 17, y + 6, 3, colour, filled=True)
    canvas.rect(x + 2, y + 6, 18, 3, colour)


def _shadowed(canvas: Canvas, x: int, y: int, text: str, font, colour) -> None:
    canvas.text(x + 1, y + 1, text, font, (0, 0, 0))
    canvas.text(x, y, text, font, colour)


_IP_LOOKUP = "https://ipwho.is/?fields=success,city,region,country,latitude,longitude"


def locate(fetch: Callable[[str], dict] = _http_json, zone: str | None = None) -> dict | None:
    """Approximate city: by IP (only when the user asks), else the city of the time zone."""
    try:
        data = fetch(_IP_LOOKUP)
        if data.get("success") and data.get("city"):
            detail = ", ".join(part for part in (data.get("region"), data.get("country")) if part)
            return {"name": str(data["city"]), "detail": detail, "lat": float(data["latitude"]), "lon": float(data["longitude"])}
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        pass
    if zone and "/" in zone:
        found = search_cities(zone.rsplit("/", 1)[-1].replace("_", " "), fetch=fetch)
        if found:
            return found[0]
    return None
