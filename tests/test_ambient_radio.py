import io
import json

from ambient.adapters import radio_browser as rb


class FakeResponse(io.BytesIO):
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


STATIONS = [
    {"stationuuid": "u1", "name": "Lofi 24/7", "url_resolved": "https://s.test/lofi", "favicon": "https://s.test/i.png",
     "country": "France", "countrycode": "FR", "tags": "lofi,chill", "codec": "MP3", "bitrate": 128, "hls": 0, "lastcheckok": 1},
    {"stationuuid": "u2", "name": "Broken", "url_resolved": "https://s.test/b", "hls": 0, "lastcheckok": 0},
    {"stationuuid": "u3", "name": "HLS", "url_resolved": "https://s.test/h.m3u8", "hls": 1, "lastcheckok": 1},
    {"stationuuid": "u4", "name": "Plain", "url_resolved": "ftp://s.test/x", "hls": 0, "lastcheckok": 1},
]


def make_opener(payload, calls):
    def opener(request, timeout):
        calls.append(request.full_url)
        assert request.headers["User-agent"].startswith("PanelDeControl/")
        return FakeResponse(json.dumps(payload).encode())
    return opener


def test_search_filters_unplayable_and_maps_fields():
    calls = []
    stations = rb.search("lofi", opener=make_opener(STATIONS, calls), host="de1.api.radio-browser.info")
    assert [s["id"] for s in stations] == ["u1"]
    assert stations[0] == {
        "id": "u1", "name": "Lofi 24/7", "url": "https://s.test/lofi", "favicon": "https://s.test/i.png",
        "country": "France", "countryCode": "FR", "tags": ["lofi", "chill"], "codec": "MP3", "bitrate": 128,
    }
    assert "name=lofi" in calls[0] and "hidebroken=true" in calls[0] and "limit=30" in calls[0]


def test_search_limit_is_capped():
    calls = []
    rb.search("x", limit=500, opener=make_opener([], calls), host="h")
    assert "limit=50" in calls[0]


def test_top_by_tag():
    calls = []
    rb.top(tag="lofi", opener=make_opener(STATIONS[:1], calls), host="h")
    assert "/json/stations/search?" in calls[0] and "tag=lofi" in calls[0] and "order=clickcount" in calls[0]


def test_resolve_returns_station_or_none():
    assert rb.resolve("u1", opener=make_opener(STATIONS[:1], []), host="h")["url"] == "https://s.test/lofi"
    assert rb.resolve("u2", opener=make_opener([STATIONS[1]], []), host="h") is None


def test_network_error_yields_empty():
    def opener(request, timeout):
        raise OSError("down")
    assert rb.search("x", opener=opener, host="h") == []


def test_pick_host_prefers_resolved_then_fallback():
    assert rb.pick_host(lambda: ["a.api.radio-browser.info"]) == "a.api.radio-browser.info"
    assert rb.pick_host(lambda: []) == rb.FALLBACK_HOST
    def boom():
        raise OSError
    assert rb.pick_host(boom) == rb.FALLBACK_HOST


def test_countries_merge_and_sort():
    rows = [
        {"name": "Germany", "iso_3166_1": "DE", "stationcount": 3000},
        {"name": "Spain", "iso_3166_1": "ES", "stationcount": 1200},
        {"name": "Deutschland", "iso_3166_1": "de", "stationcount": 5},
        {"name": "Nowhere", "iso_3166_1": "", "stationcount": 9},
        {"name": "Empty", "iso_3166_1": "XX", "stationcount": 0},
    ]
    calls = []
    assert rb.countries(opener=make_opener(rows, calls), host="h") == [
        {"code": "DE", "name": "Germany", "count": 3000},
        {"code": "ES", "name": "Spain", "count": 1200},
    ]
    assert "/json/countries?" in calls[0]


def test_tags_keep_named_non_empty():
    rows = [{"name": "pop", "stationcount": 900}, {"name": " ", "stationcount": 5}, {"name": "dead", "stationcount": 0}]
    assert rb.tags(opener=make_opener(rows, []), host="h") == [{"name": "pop", "count": 900}]


def test_discover_maps_filters_and_ignores_unsafe_values():
    calls = []
    rb.discover({"name": "lofi", "country": "es", "tag": "Chill", "language": "spanish", "minBitrate": 128,
                 "order": "trending", "offset": 30, "limit": 999}, opener=make_opener(STATIONS, calls), host="h")
    url = calls[0]
    for part in ("name=lofi", "countrycode=ES", "tag=chill", "language=spanish", "bitrateMin=128", "order=clicktrend", "offset=30", "limit=50"):
        assert part in url
    calls.clear()
    rb.discover({"country": "ESP", "minBitrate": True, "order": "drop table", "offset": -1}, opener=make_opener([], calls), host="h")
    assert "countrycode" not in calls[0] and "bitrateMin" not in calls[0] and "offset" not in calls[0] and "order=clickcount" in calls[0]


def test_geo_is_kept_only_when_valid_and_can_be_required():
    rows = [
        {**STATIONS[0], "stationuuid": "g1", "geo_lat": 40.4168, "geo_long": -3.7038},
        {**STATIONS[0], "stationuuid": "g2", "geo_lat": 0, "geo_long": 0},
        {**STATIONS[0], "stationuuid": "g3", "geo_lat": "40", "geo_long": 3},
        {**STATIONS[0], "stationuuid": "g4", "geo_lat": 95, "geo_long": 3},
    ]
    calls = []
    stations = rb.discover({"hasGeo": True, "country": "ES"}, opener=make_opener(rows, calls), host="h")
    assert "has_geo_info=true" in calls[0]
    assert [s.get("geo") for s in stations] == [[40.4168, -3.7038], None, None, None]


def test_near_searches_by_distance_and_ignores_bad_points():
    calls = []
    rb.discover({"near": {"lat": 37.389, "lon": -5.984, "radiusKm": 30}}, opener=make_opener([], calls), host="h")
    for part in ("geo_lat=37.389", "geo_long=-5.984", "geo_distance=30000", "has_geo_info=true"):
        assert part in calls[0]
    calls.clear()
    rb.discover({"near": {"lat": 120, "lon": 0, "radiusKm": 30}}, opener=make_opener([], calls), host="h")
    rb.discover({"near": {"lat": 1, "lon": 1, "radiusKm": 99999}}, opener=make_opener([], calls), host="h")
    assert "geo_lat" not in calls[0] and "geo_distance=2000000" in calls[1]


def test_map_queries_may_ask_for_more_in_one_request():
    calls = []
    rb.discover({"hasGeo": True, "limit": 150}, opener=make_opener([], calls), host="h")
    rb.discover({"limit": 150}, opener=make_opener([], calls), host="h")
    assert "limit=150" in calls[0] and "limit=50" in calls[1]
