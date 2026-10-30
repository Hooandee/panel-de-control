from __future__ import annotations

import copy
import re
from typing import Any

SETTINGS_VERSION = 1

INTERVALS_SEC = (30, 60, 300, 900, 3600)
ORDERS = ("sequential", "shuffle")
TRANSITIONS = ("fade", "kenburns")
GAME_ART_MODES = ("mine", "blend", "game")
MUSIC_SOURCES = ("music", "radio")
IN_GAME_ACTIONS = ("pause", "continue", "duck")
OVERLAY_MODES = ("off", "peek", "always")
OVERLAY_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
VIDEO_SIZES = ("small", "medium", "large")
_SIZE_SCALE = {"small": 30, "medium": 40, "large": 52}
_ACTION_LEVEL = {"pause": 0, "duck": 30, "continue": 100}
VIDEO_SCALE_RANGE = (20, 70)
VIDEO_QUALITIES = ("fluid", "saver", "sharp")
CLAIM_OWNERS = ("panel", "theme", "other")

_APPID = re.compile(r"^[0-9]{1,10}$")
_MEDIA_REF = re.compile(r"^(local|url|opt|steam|remote):[A-Za-z0-9._:/?&=%+~@#!$'()*,;-]{1,2048}$")
_SELECTED_REF = re.compile(r"(?:local|steam|remote):[A-Za-z0-9._:/?&=%+~@#!$'()*,;-]{1,2048}")
_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_CLAIM_KEY = re.compile(r"^(css:[A-Za-z]{1,48}(::before|::after)?|[A-Za-z0-9._-]{1,64})$")
_MAX_ITEMS = 200
_MAX_PLAYLISTS = 20

DEFAULTS: dict[str, Any] = {
    "version": SETTINGS_VERSION,
    "background": {
        "enabled": False,
        "collections": ["suggested.library"],
        "intervalSec": 300,
        "onReturnHome": False,
        "order": "shuffle",
        "transition": "fade",
        "gameArt": "blend",
        "library": False,
        "perGame": {},
        "pinned": "",
        "selectedRefs": [],
        "gameTrailers": False,
        "gameThemes": False,
        "lowBatteryPercent": 20,
        "optimizeVideos": True,
        "videoQuality": "fluid",
    },
    "music": {
        "enabled": False,
        "source": "radio",
        "volume": 0.5,
        "inGameMusic": "pause",
        "inGameRadio": "continue",
        "qamPlayer": True,
        "videoOn": False,
        "overlay": "peek",
        "overlayCorner": "top-right",
        "videoSize": "medium",
        "videoScale": 40,
        "inGameMusicLevel": 0,
        "inGameRadioLevel": 100,
        "inGameMediaLevel": 100,
        "inGameGameLevel": 100,
        "folders": [],
        "lastTrack": None,
        "stationId": None,
    },
    "collections": {"removedSuggested": [], "favorites": [], "folders": []},
    "radio": {"removedSuggested": [], "favorites": [], "playlists": []},
    "claims": {},
}


def default_settings() -> dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def normalize_settings(raw: Any) -> dict[str, Any]:
    out = default_settings()
    if not isinstance(raw, dict):
        return out
    version = raw.get("version", SETTINGS_VERSION)
    if version != SETTINGS_VERSION:
        return out
    _normalize_background(out["background"], _dict(raw.get("background")))
    _normalize_music(out["music"], _dict(raw.get("music")))
    _normalize_collections(out["collections"], _dict(raw.get("collections")))
    _normalize_radio(out["radio"], _dict(raw.get("radio")))
    out["claims"] = {
        key: value
        for key, value in _dict(raw.get("claims")).items()
        if isinstance(key, str) and _CLAIM_KEY.match(key) and value in CLAIM_OWNERS
    }
    return out


def _normalize_background(out: dict[str, Any], raw: dict[str, Any]) -> None:
    _bool(out, raw, "enabled")
    _bool(out, raw, "onReturnHome")
    _bool(out, raw, "library")
    _bool(out, raw, "optimizeVideos")
    _bool(out, raw, "gameTrailers")
    _bool(out, raw, "gameThemes")
    _enum(out, raw, "videoQuality", VIDEO_QUALITIES)
    _enum(out, raw, "order", ORDERS)
    _enum(out, raw, "transition", TRANSITIONS)
    _enum(out, raw, "gameArt", GAME_ART_MODES)
    collections = raw.get("collections")
    if isinstance(collections, list):
        out["collections"] = _unique([c for c in collections if isinstance(c, str) and _ID.match(c)])
    interval = raw.get("intervalSec")
    if _number(interval):
        out["intervalSec"] = _nearest_interval(interval)
    threshold = raw.get("lowBatteryPercent")
    if _number(threshold):
        out["lowBatteryPercent"] = int(min(50, max(5, threshold)))
    out["perGame"] = {
        key: value
        for key, value in _dict(raw.get("perGame")).items()
        if isinstance(key, str) and _APPID.match(key) and isinstance(value, str) and _MEDIA_REF.match(value)
    }
    pinned = raw.get("pinned")
    out["pinned"] = pinned if isinstance(pinned, str) and _MEDIA_REF.match(pinned) else ""
    selected = raw.get("selectedRefs")
    if isinstance(selected, list):
        out["selectedRefs"] = _unique([ref for ref in selected if isinstance(ref, str) and _SELECTED_REF.fullmatch(ref)])


def _normalize_music(out: dict[str, Any], raw: dict[str, Any]) -> None:
    _bool(out, raw, "enabled")
    _enum(out, raw, "source", MUSIC_SOURCES)
    _enum(out, raw, "inGameMusic", IN_GAME_ACTIONS)
    _enum(out, raw, "inGameRadio", IN_GAME_ACTIONS)
    _bool(out, raw, "qamPlayer")
    _bool(out, raw, "videoOn")
    _enum(out, raw, "overlay", OVERLAY_MODES)
    _enum(out, raw, "overlayCorner", OVERLAY_CORNERS)
    _enum(out, raw, "videoSize", VIDEO_SIZES)
    out["videoScale"] = _level(raw.get("videoScale"), _SIZE_SCALE[out["videoSize"]], *VIDEO_SCALE_RANGE)
    out["inGameMusicLevel"] = _level(raw.get("inGameMusicLevel"), _ACTION_LEVEL[out["inGameMusic"]], 0, 100)
    out["inGameRadioLevel"] = _level(raw.get("inGameRadioLevel"), _ACTION_LEVEL[out["inGameRadio"]], 0, 100)
    out["inGameMediaLevel"] = _level(raw.get("inGameMediaLevel"), out["inGameRadioLevel"], 0, 100)
    out["inGameGameLevel"] = _level(raw.get("inGameGameLevel"), 100, 0, 100)
    volume = raw.get("volume")
    if _number(volume):
        out["volume"] = float(min(1.0, max(0.0, volume)))
    out["folders"] = _folders(raw.get("folders"))
    track = raw.get("lastTrack")
    if isinstance(track, dict) and isinstance(track.get("id"), str) and _number(track.get("position")):
        out["lastTrack"] = {"id": track["id"][:128], "position": max(0.0, float(track["position"]))}
    station = raw.get("stationId")
    if isinstance(station, str) and _ID.match(station):
        out["stationId"] = station


def _normalize_collections(out: dict[str, Any], raw: dict[str, Any]) -> None:
    out["removedSuggested"] = _ids(raw.get("removedSuggested"))
    out["favorites"] = _favorites(raw.get("favorites"))
    out["folders"] = _folders(raw.get("folders"))


def _normalize_radio(out: dict[str, Any], raw: dict[str, Any]) -> None:
    out["removedSuggested"] = _ids(raw.get("removedSuggested"))
    out["favorites"] = _favorites(raw.get("favorites"))
    out["playlists"] = [{k: p[k] for k in ("id", "name", "url")} for p in _favorites(raw.get("playlists"))][:_MAX_PLAYLISTS]


def _favorites(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fav_id, name, url = item.get("id"), item.get("name"), item.get("url")
        if not (isinstance(fav_id, str) and _ID.match(fav_id)):
            continue
        if not (isinstance(url, str) and url.startswith(("https://", "http://")) and len(url) <= 2048):
            continue
        if url in seen:
            continue
        seen.add(url)
        entry = {"id": fav_id, "name": name[:80] if isinstance(name, str) and name.strip() else url[:80], "url": url}
        art, subtitle = item.get("art"), item.get("subtitle")
        if isinstance(art, str) and art.startswith("https://") and len(art) <= 2048:
            entry["art"] = art
        if isinstance(subtitle, str) and subtitle.strip():
            entry["subtitle"] = subtitle.strip()[:80]
        result.append(entry)
    return result[:_MAX_ITEMS]


def _level(value: Any, fallback: int, low: int, high: int) -> int:
    """A 0–100 style level; settings saved before levels existed derive it from their old choice."""
    if not _number(value):
        return fallback
    return int(min(high, max(low, round(value))))


def _folders(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return _unique([f for f in raw if isinstance(f, str) and f.startswith("/") and len(f) < 4096])[:_MAX_ITEMS]


def _nearest_interval(value: float) -> int:
    return min(INTERVALS_SEC, key=lambda allowed: (abs(allowed - value), -allowed))


def _ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return _unique([i for i in raw if isinstance(i, str) and _ID.match(i)])[:_MAX_ITEMS]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _bool(out: dict[str, Any], raw: dict[str, Any], key: str) -> None:
    if isinstance(raw.get(key), bool):
        out[key] = raw[key]


def _enum(out: dict[str, Any], raw: dict[str, Any], key: str, allowed: tuple[str, ...]) -> None:
    if raw.get(key) in allowed:
        out[key] = raw[key]
