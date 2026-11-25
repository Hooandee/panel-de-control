import io
import json
import urllib.parse

import pytest

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
    assert [s["id"] for s in stations] == ["u1", "u3"]
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


def test_network_error_is_distinct_from_empty():
    def opener(request, timeout):
        raise OSError("down")
    with pytest.raises(RuntimeError, match="radio_unreachable"):
        rb.search("x", opener=opener, host="h")


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


@pytest.mark.parametrize("method,args", [(rb.search, ("private search",)), (rb.discover, ({"name": "private search"},)), (rb.countries, ()), (rb.tags, ()), (rb.resolve, ("private-id",))])
def test_failed_server_tries_another_and_empty_success_stops(monkeypatch, method, args):
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test", "third.test"], raising=False)
    seen = []
    def opener(request, timeout):
        seen.append(urllib.parse.urlsplit(request.full_url).hostname)
        assert 0 < timeout <= 3
        if len(seen) == 1:
            raise TimeoutError("secret stream?token=private")
        return FakeResponse(b"[]")
    assert method(*args, opener=opener) == (None if method is rb.resolve else [])
    assert seen == ["first.test", "second.test"]


def test_exhausted_servers_raise_safe_error_and_bound_attempts(monkeypatch):
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test", "third.test"], raising=False)
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        raise OSError("https://private.test/stream?secret=1")
    with pytest.raises(RuntimeError, match="radio_unreachable") as caught:
        rb.discover({"name": "private query"}, opener=opener)
    assert len(calls) == 2
    assert "OSError" in str(caught.value) and "second.test" in str(caught.value)
    assert "private" not in str(caught.value) and "secret" not in str(caught.value)


def test_invalid_response_retries_instead_of_returning_empty(monkeypatch):
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test"], raising=False)
    replies = iter([b'{"error":"down"}', json.dumps(STATIONS[:1]).encode()])
    assert rb.search(opener=lambda request, timeout: FakeResponse(next(replies)))[0]["id"] == "u1"


def test_hls_requires_a_path_the_player_recognizes():
    rows = [{**STATIONS[2], "url_resolved": url} for url in [
        "https://s.test/live.M3U8?token=secret#live", "https://s.test/live?format=.m3u8", "https://s.test/live",
    ]]
    stations = rb.search(opener=make_opener(rows, []), host="h")
    assert [s["url"] for s in stations] == [rows[0]["url_resolved"]]


def test_discovery_blocked_reuses_one_worker_and_cached_result(monkeypatch):
    import threading
    gate = threading.Event()
    started = threading.Event()
    calls = []
    def resolver():
        calls.append(1)
        started.set()
        gate.wait(2)
        return ["discovered.api.radio-browser.info"]
    monkeypatch.setattr(rb, "_dns_hosts", resolver)
    monkeypatch.setattr(rb, "DISCOVERY_WAIT_SEC", 0.01, raising=False)
    try:
        for _ in range(3):
            assert rb.FALLBACK_HOST in rb._candidate_hosts()
        assert started.is_set() and calls == [1]
    finally:
        gate.set()
    assert rb._discovery_done.wait(1)
    assert "discovered.api.radio-browser.info" in rb._candidate_hosts()
    assert calls == [1]


def test_request_budget_stops_retry_after_slow_attempt(monkeypatch):
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test"])
    clock = [100.0]
    monkeypatch.setattr(rb.time, "monotonic", lambda: clock[0])
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        clock[0] += 7
        raise TimeoutError("slow")
    with pytest.raises(RuntimeError, match="radio_unreachable"):
        rb.search(opener=opener)
    assert len(calls) == 1


def test_failed_attempt_logs_only_host_and_class(monkeypatch, caplog):
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test"])
    attempts = []
    def opener(request, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("https://private.test/stream?secret=1")
        return FakeResponse(b"[]")
    assert rb.search("private query", opener=opener) == []
    assert "first.test" in caplog.text and "TimeoutError" in caplog.text
    assert "private" not in caplog.text and "secret" not in caplog.text


def test_truncated_http_response_retries_another_server(monkeypatch):
    from http.client import IncompleteRead
    monkeypatch.setattr(rb, "_candidate_hosts", lambda: ["first.test", "second.test"])
    class TruncatedResponse(FakeResponse):
        def read(self, size=-1):
            raise IncompleteRead(b'{"private":"stream-url"', 40)
    responses = iter([TruncatedResponse(), FakeResponse(json.dumps(STATIONS[:1]).encode())])
    assert rb.search(opener=lambda request, timeout: next(responses))[0]["id"] == "u1"


def test_malformed_hls_url_does_not_discard_other_stations():
    rows = [{**STATIONS[2], "url_resolved": "https://[broken/live.m3u8"}, STATIONS[0]]
    assert [s["id"] for s in rb.search(opener=make_opener(rows, []), host="h")] == ["u1"]
