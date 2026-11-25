from datetime import timezone

import pytest

from accessories.jsaux_pixel import codec, weather
from accessories.jsaux_pixel.scenes.base import SceneContext
from accessories.jsaux_pixel.scenes.fit import encoded_size

SEVILLE = {"name": "Sevilla", "lat": 37.39, "lon": -5.99}


class Fetch:
    def __init__(self, payloads):
        self.payloads, self.urls = payloads, []

    def __call__(self, url):
        self.urls.append(url)
        for marker, payload in self.payloads.items():
            if marker in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise OSError("offline")


FORECAST = {"current": {"temperature_2m": 23.6, "weather_code": 61, "is_day": 1},
            "daily": {"temperature_2m_max": [27.2], "temperature_2m_min": [15.8]}}


def test_city_search_returns_names_and_coordinates():
    fetch = Fetch({"geocoding-api": {"results": [
        {"name": "Sevilla", "country": "España", "admin1": "Andalucía", "latitude": 37.38, "longitude": -5.97}]}})
    cities = weather.search_cities("Sevi", fetch=fetch)
    assert cities == [{"name": "Sevilla", "detail": "Andalucía, España", "lat": 37.38, "lon": -5.97}]
    assert "name=Sevi" in fetch.urls[0]


def test_search_failure_is_an_empty_list():
    assert weather.search_cities("x", fetch=Fetch({})) == []


def test_forecast_is_cached_for_half_an_hour():
    fetch = Fetch({"api.open-meteo.com": FORECAST})
    source = weather.WeatherSource(fetch=fetch, clock=lambda: 1000.0, spawn=lambda fn: fn())
    first = source.current(SEVILLE)
    assert first == {"temp": 23.6, "code": 61, "day": True, "high": 27.2, "low": 15.8}
    source.current(SEVILLE)
    assert len(fetch.urls) == 1


def test_offline_keeps_the_last_good_reading():
    clock = [1000.0]
    fetch = Fetch({"api.open-meteo.com": FORECAST})
    source = weather.WeatherSource(fetch=fetch, clock=lambda: clock[0], spawn=lambda fn: fn())
    source.current(SEVILLE)
    fetch.payloads = {}
    clock[0] += 3600
    assert source.current(SEVILLE)["temp"] == 23.6


@pytest.mark.parametrize("code,group", [(0, "clear"), (2, "cloud"), (45, "fog"), (63, "rain"), (75, "snow"), (95, "storm")])
def test_weather_codes_map_to_animations(code, group):
    assert weather.group_for(code) == group


@pytest.mark.parametrize("group", ["clear", "cloud", "fog", "rain", "snow", "storm"])
@pytest.mark.parametrize("day", [True, False])
def test_every_weather_animation_loops_within_size(group, day):
    scene = weather.WeatherScene(source=None)
    reading = {"temp": 18.0, "code": weather.SAMPLE_CODES[group], "day": day, "high": 21.0, "low": 9.0}
    segment = scene.render_reading(reading, {"city": SEVILLE})
    assert len(segment.frames) >= 8
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_scene_without_city_asks_for_one_without_network():
    fetch = Fetch({})
    scene = weather.WeatherScene(source=weather.WeatherSource(fetch=fetch, clock=lambda: 0.0, spawn=lambda fn: fn()))
    ctx = SceneContext(now=0.0, tz=timezone.utc, options={})
    scene.key(ctx)
    assert scene.render(ctx).frames
    assert fetch.urls == []


def test_temperature_jitter_does_not_rewrite_the_panel():
    readings = iter([{"temp": t, "code": 0, "day": True, "high": 25.0, "low": 12.0} for t in (20.2, 20.6, 20.4, 21.4, 20.5)])

    class Source:
        def current(self, city):
            return next(readings)

    scene = weather.WeatherScene(source=Source())
    ctx = SceneContext(now=0.0, tz=timezone.utc, options={"city": SEVILLE})
    keys = [scene.key(ctx) for _ in range(5)]
    assert len(set(keys)) == 2


def test_fetch_runs_in_the_background_and_never_blocks_the_caller():
    started = []
    fetch = Fetch({"api.open-meteo.com": FORECAST})
    source = weather.WeatherSource(fetch=fetch, clock=lambda: 1000.0, spawn=started.append)
    assert source.current(SEVILLE) is None
    assert fetch.urls == [] and len(started) == 1
    started[0]()
    assert source.current(SEVILLE)["temp"] == 23.6


def test_failures_back_off_instead_of_retrying_every_tick():
    clock = [1000.0]
    fetch = Fetch({})
    source = weather.WeatherSource(fetch=fetch, clock=lambda: clock[0], spawn=lambda fn: fn())
    for _ in range(100):
        source.current(SEVILLE)
        clock[0] += 1
    assert len(fetch.urls) == 1
    clock[0] += 300
    source.current(SEVILLE)
    assert len(fetch.urls) == 2


def test_weather_is_not_ready_while_its_first_fetch_is_in_flight():
    pending = []
    source = weather.WeatherSource(fetch=Fetch({"api.open-meteo.com": FORECAST}), clock=lambda: 0.0, spawn=pending.append)
    scene = weather.WeatherScene(source=source)
    ctx = SceneContext(now=0.0, tz=timezone.utc, options={"city": SEVILLE})
    scene.key(ctx)
    assert scene.render(ctx).ready is False
    pending[0]()
    scene.key(ctx)
    assert scene.render(ctx).ready is True


def test_weather_shows_its_placeholder_once_the_fetch_has_failed():
    source = weather.WeatherSource(fetch=Fetch({}), clock=lambda: 0.0, spawn=lambda fn: fn())
    scene = weather.WeatherScene(source=source)
    ctx = SceneContext(now=0.0, tz=timezone.utc, options={"city": SEVILLE})
    scene.key(ctx)
    assert scene.render(ctx).ready is True


@pytest.mark.parametrize("group", ["clear", "cloud", "fog", "rain", "snow", "storm"])
@pytest.mark.parametrize("day", [True, False])
def test_sky_style_fills_the_display_and_fits(group, day):
    scene = weather.WeatherScene(source=None)
    reading = {"temp": 18.0, "code": weather.SAMPLE_CODES[group], "day": day, "high": 21.0, "low": 9.0}
    segment = scene.render_reading(reading, {"city": SEVILLE, "style": "sky"})
    lit = sum(1 for p in segment.frames[0].pixels() if p != (0, 0, 0))
    assert lit > 64 * 54 * 0.6
    assert encoded_size(segment) <= codec.MAX_GIF_BYTES


def test_locate_uses_ip_lookup_when_asked():
    fetch = Fetch({"ipwho.is": {"success": True, "city": "Sevilla", "region": "Andalucía", "country": "España",
                                "latitude": 37.39, "longitude": -5.98}})
    assert weather.locate(fetch=fetch) == {"name": "Sevilla", "detail": "Andalucía, España", "lat": 37.39, "lon": -5.98}


def test_locate_falls_back_to_the_time_zone_city():
    fetch = Fetch({"geocoding-api": {"results": [
        {"name": "Madrid", "country": "España", "admin1": "Madrid", "latitude": 40.4, "longitude": -3.7}]}})
    assert weather.locate(fetch=fetch, zone="Europe/Madrid")["name"] == "Madrid"


def test_locate_gives_up_cleanly():
    assert weather.locate(fetch=Fetch({}), zone=None) is None


def test_negative_temperature_draws_its_minus_sign():
    from accessories.jsaux_pixel.render.canvas import Canvas

    plain, cold = Canvas(), Canvas()
    weather._degrees(plain, "5", 6)
    weather._degrees(cold, "-5", 6)
    assert cold.pixels() != plain.pixels()
    bar_row = 6 + 6
    assert any(cold.get(x, bar_row) != (0, 0, 0) for x in range(64))
