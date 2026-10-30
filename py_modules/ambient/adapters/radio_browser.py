from __future__ import annotations

import json
import logging
import random
import socket
import threading
import time
import urllib.parse
from http.client import HTTPException
from typing import Any, Callable, Optional

from .remote_sources import Opener, build_request, default_opener

FALLBACK_HOST = "de1.api.radio-browser.info"
MAX_LIMIT = 50
MAX_GEO_LIMIT = 150
DEFAULT_LIMIT = 30
TIMEOUT_SEC = 3.0
MAX_ATTEMPTS = 2
REQUEST_BUDGET_SEC = 6.0
DISCOVERY_WAIT_SEC = 1.0
DISCOVERY_TTL_SEC = 3600.0
_discovery_lock = threading.Lock()
_discovery_done = threading.Event()
_discovery_done.set()
_discovered_hosts: list[str] = []
_discovery_at = 0.0


class RadioBrowserError(RuntimeError):
    def __init__(self, host: str, error_class: str):
        self.host = host
        self.error_class = error_class
        super().__init__(f"radio_unreachable:{host}:{error_class}")


def _dns_hosts() -> list[str]:
    infos = socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP)
    hosts = []
    for info in infos:
        try:
            name = socket.gethostbyaddr(info[4][0])[0]
        except OSError:
            continue
        if name.endswith(".api.radio-browser.info") and name not in hosts:
            hosts.append(name)
    return hosts


def _refresh_hosts() -> None:
    global _discovered_hosts, _discovery_at
    hosts = []
    try:
        hosts = _dns_hosts()
    except OSError:
        hosts = []
    finally:
        with _discovery_lock:
            _discovered_hosts = hosts
            _discovery_at = time.monotonic()
            _discovery_done.set()


def _candidate_hosts() -> list[str]:
    with _discovery_lock:
        ttl = DISCOVERY_TTL_SEC if _discovered_hosts else 60.0
        if _discovery_done.is_set() and (not _discovery_at or time.monotonic() - _discovery_at >= ttl):
            _discovery_done.clear()
            threading.Thread(target=_refresh_hosts, name="ambient-radio-dns", daemon=True).start()
    _discovery_done.wait(DISCOVERY_WAIT_SEC)
    with _discovery_lock:
        hosts = list(_discovered_hosts)
    random.shuffle(hosts)
    return list(dict.fromkeys([*hosts, FALLBACK_HOST, "all.api.radio-browser.info"]))


def pick_host(resolver: Callable[[], list[str]] = _dns_hosts) -> str:
    try:
        hosts = resolver()
    except OSError:
        hosts = []
    return random.choice(hosts) if hosts else FALLBACK_HOST


def _playable(entry: Any) -> Optional[dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    url = entry.get("url_resolved")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return None
    if not entry.get("lastcheckok"):
        return None
    if entry.get("hls"):
        try:
            if not urllib.parse.urlsplit(url).path.lower().endswith(".m3u8"):
                return None
        except ValueError:
            return None
    tags = entry.get("tags") if isinstance(entry.get("tags"), str) else ""
    geo = _geo(entry)
    station = {
        "id": str(entry.get("stationuuid", ""))[:64],
        "name": str(entry.get("name", "")).strip()[:120] or url,
        "url": url,
        "favicon": entry.get("favicon") if isinstance(entry.get("favicon"), str) and entry["favicon"].startswith("https://") else "",
        "country": str(entry.get("country", ""))[:60],
        "countryCode": str(entry.get("countrycode", ""))[:2],
        "tags": [t for t in (x.strip() for x in tags.split(",")) if t][:6],
        "codec": str(entry.get("codec", ""))[:12],
        "bitrate": int(entry.get("bitrate") or 0),
    }
    if geo:
        station["geo"] = geo
    return station


def _geo(entry: dict[str, Any]) -> Optional[list[float]]:
    lat, lon = entry.get("geo_lat"), entry.get("geo_long")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return [round(float(lat), 4), round(float(lon), 4)]


def _query(path: str, params: dict[str, Any], opener: Opener, host: Optional[str]) -> list[dict[str, Any]]:
    return [s for s in (_playable(e) for e in _fetch_list(path, params, opener, host)) if s and s["id"]]


def _limit(limit: int) -> int:
    return max(1, min(MAX_LIMIT, int(limit)))


ORDERS = {"popular": "clickcount", "trending": "clicktrend", "votes": "votes", "quality": "bitrate"}


def _fetch_list(path: str, params: dict[str, Any], opener: Opener, host: Optional[str]) -> list[Any]:
    hosts = [host] if host else _candidate_hosts()
    deadline = time.monotonic() + REQUEST_BUDGET_SEC
    last_error = RadioBrowserError(hosts[0], "TimeoutError")
    for candidate in hosts[:MAX_ATTEMPTS]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        url = f"https://{candidate}/json/{path}?{urllib.parse.urlencode(params)}"
        try:
            with opener(build_request(url), min(TIMEOUT_SEC, remaining)) as response:
                data = json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError("invalid_list")
            return data
        except (OSError, ValueError, HTTPException) as error:
            last_error = RadioBrowserError(candidate, type(error).__name__)
            logging.getLogger(__name__).warning("Radio Browser failed: host=%s class=%s", candidate, last_error.error_class)
    raise last_error from None


def countries(opener: Opener = default_opener, host: Optional[str] = None) -> list[dict[str, Any]]:
    """Countries with at least one working station, most stations first."""
    rows = _fetch_list("countries", {"hidebroken": "true", "order": "stationcount", "reverse": "true"}, opener, host)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("iso_3166_1") or "").upper()[:2]
        count = int(row.get("stationcount") or 0)
        if len(code) != 2 or not code.isalpha() or count <= 0:
            continue
        current = result.get(code)
        if current is None or count > current["count"]:
            result[code] = {"code": code, "name": str(row.get("name", code))[:60], "count": count}
    return sorted(result.values(), key=lambda c: -c["count"])


def tags(limit: int = 80, opener: Opener = default_opener, host: Optional[str] = None) -> list[dict[str, Any]]:
    rows = _fetch_list("tags", {"hidebroken": "true", "order": "stationcount", "reverse": "true", "limit": max(1, min(200, int(limit)))}, opener, host)
    return [
        {"name": str(row["name"])[:40], "count": int(row.get("stationcount") or 0)}
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"].strip() and int(row.get("stationcount") or 0) > 0
    ]


def discover(filters: dict[str, Any], opener: Opener = default_opener, host: Optional[str] = None) -> list[dict[str, Any]]:
    """Search with every filter Radio Browser offers; unknown or unsafe values are ignored."""
    geo = filters.get("hasGeo") is True or isinstance(filters.get("near"), dict)
    raw_limit = filters.get("limit", DEFAULT_LIMIT)
    limit = max(1, min(MAX_GEO_LIMIT if geo else MAX_LIMIT, int(raw_limit))) if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else DEFAULT_LIMIT
    params: dict[str, Any] = {"hidebroken": "true", "reverse": "true", "limit": limit}
    params["order"] = ORDERS.get(str(filters.get("order", "popular")), "clickcount")
    name = filters.get("name")
    if isinstance(name, str) and name.strip():
        params["name"] = name.strip()[:80]
    country = filters.get("country")
    if isinstance(country, str) and len(country) == 2 and country.isalpha():
        params["countrycode"] = country.upper()
    tag = filters.get("tag")
    if isinstance(tag, str) and tag.strip():
        params["tag"] = tag.strip().lower()[:40]
    language = filters.get("language")
    if isinstance(language, str) and language.strip():
        params["language"] = language.strip().lower()[:30]
    bitrate = filters.get("minBitrate")
    if isinstance(bitrate, int) and not isinstance(bitrate, bool) and 0 < bitrate <= 512:
        params["bitrateMin"] = bitrate
    if filters.get("hasGeo") is True:
        params["has_geo_info"] = "true"
    near = filters.get("near")
    if isinstance(near, dict) and all(isinstance(near.get(k), (int, float)) and not isinstance(near.get(k), bool) for k in ("lat", "lon", "radiusKm")):
        if -90 <= near["lat"] <= 90 and -180 <= near["lon"] <= 180:
            params["geo_lat"] = round(float(near["lat"]), 4)
            params["geo_long"] = round(float(near["lon"]), 4)
            params["geo_distance"] = int(min(2000, max(1, near["radiusKm"])) * 1000)
            params["has_geo_info"] = "true"
    offset = filters.get("offset")
    if isinstance(offset, int) and not isinstance(offset, bool) and 0 < offset <= 5000:
        params["offset"] = offset
    return [s for s in (_playable(e) for e in _fetch_list("stations/search", params, opener, host)) if s and s["id"]]


def search(name: str = "", country: str = "", tag: str = "", limit: int = DEFAULT_LIMIT,
           opener: Opener = default_opener, host: Optional[str] = None) -> list[dict[str, Any]]:
    params = {"name": name[:80], "countrycode": country[:2], "tag": tag[:40], "limit": _limit(limit),
              "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    return _query("stations/search", {k: v for k, v in params.items() if v != ""}, opener, host)


def top(tag: str = "", limit: int = DEFAULT_LIMIT, opener: Opener = default_opener,
        host: Optional[str] = None) -> list[dict[str, Any]]:
    return search(tag=tag, limit=limit, opener=opener, host=host)


def resolve(station_id: str, opener: Opener = default_opener, host: Optional[str] = None) -> Optional[dict[str, Any]]:
    found = _query("stations/byuuid", {"uuids": station_id[:64]}, opener, host)
    return found[0] if found else None
