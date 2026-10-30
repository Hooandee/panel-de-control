from __future__ import annotations

import copy
import hashlib
import os
from typing import Any, Literal

from .settings import normalize_settings

Scope = Literal["background", "radio"]

SUGGESTED_BACKGROUNDS: tuple[dict[str, str], ...] = (
    {"id": "suggested.library", "kind": "suggested", "source": "steam-library"},
    {"id": "suggested.nasa", "kind": "suggested", "source": "nasa-apod"},
    {"id": "suggested.bing", "kind": "suggested", "source": "bing-daily"},
)

SUGGESTED_STATION_TAGS: tuple[str, ...] = ("lofi", "chillout", "videogame", "synthwave")


def _store_key(scope: Scope) -> str:
    return "collections" if scope == "background" else "radio"


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}.{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def visible_backgrounds(settings: dict[str, Any]) -> list[dict[str, str]]:
    store = settings["collections"]
    removed = set(store["removedSuggested"])
    items = [dict(s) for s in SUGGESTED_BACKGROUNDS if s["id"] not in removed]
    items += [
        {"id": stable_id("folder", path), "kind": "folder", "name": os.path.basename(path.rstrip("/")) or path, "path": path}
        for path in store["folders"]
    ]
    items += [{"id": fav["id"], "kind": "favorite", "name": fav["name"], "url": fav["url"]} for fav in store["favorites"]]
    return items


def add_favorite(settings: dict[str, Any], scope: Scope, url: str, name: str, art: str = "", subtitle: str = "") -> dict[str, Any]:
    if not (isinstance(url, str) and url.startswith(("https://", "http://"))):
        return settings
    out = copy.deepcopy(settings)
    favorites = out[_store_key(scope)]["favorites"]
    if any(f["url"] == url for f in favorites):
        return out
    favorites.append({"id": stable_id("fav", url), "name": name, "url": url, "art": art, "subtitle": subtitle})
    return normalize_settings(out)


def remove_item(settings: dict[str, Any], scope: Scope, item_id: str) -> dict[str, Any]:
    out = copy.deepcopy(settings)
    store = out[_store_key(scope)]
    if item_id.startswith("suggested."):
        if item_id not in store["removedSuggested"]:
            store["removedSuggested"].append(item_id)
    store["favorites"] = [f for f in store["favorites"] if f["id"] != item_id]
    if scope == "background":
        store["folders"] = [p for p in store["folders"] if stable_id("folder", p) != item_id]
        out["background"]["collections"] = [c for c in out["background"]["collections"] if c != item_id]
    return normalize_settings(out)


def restore_suggested(settings: dict[str, Any], scope: Scope, item_id: str = "") -> dict[str, Any]:
    out = copy.deepcopy(settings)
    store = out[_store_key(scope)]
    if not item_id:
        store["removedSuggested"] = []
        return normalize_settings(out)
    if item_id in store["removedSuggested"]:
        store["removedSuggested"] = [i for i in store["removedSuggested"] if i != item_id]
        if scope == "background" and item_id not in out["background"]["collections"]:
            out["background"]["collections"].append(item_id)
    return normalize_settings(out)
