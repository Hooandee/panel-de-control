from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from json_store import atomic_json_save

from .library_scan import media_id as local_media_id

MAX_THEME_IMAGES = 128
MAX_OWNER_LENGTH = 128
_VERSION = 2


class ThemeImageStore:
    """Pictures theme runtimes chose through Ambiente's explorer, kept by path so their `local:` refs
    resolve after a reboot without a scan and whether Ambiente's own background is on or off.

    Each entry lists the themes (catalog ids) that keep it. Entries saved before owners existed have none:
    a theme adopts one by keeping it, and an omission never drops it; the oldest-first cap ages it out."""

    def __init__(self, path: str, limit: int = MAX_THEME_IMAGES):
        self._path = path
        self._limit = limit
        self._images: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self._path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        images = raw.get("images") if isinstance(raw, dict) else None
        if not isinstance(images, dict):
            return {}
        valid = {}
        for ref, entry in images.items():
            if not isinstance(entry, dict) or not valid_source(ref, entry.get("path")):
                continue
            at = entry.get("at")
            owners = entry.get("owners")
            valid[ref] = {
                "path": entry["path"],
                "at": at if isinstance(at, int) and not isinstance(at, bool) else 0,
                "owners": sorted({o for o in owners if valid_owner(o)}) if isinstance(owners, list) else [],
            }
        return self._bounded(valid)[0]

    def _bounded(self, images: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
        if len(images) <= self._limit:
            return images, []
        newest = dict(sorted(images.items(), key=lambda item: item[1]["at"], reverse=True)[: self._limit])
        return newest, [ref for ref in images if ref not in newest]

    def _save(self, images: dict[str, dict[str, Any]]) -> None:
        atomic_json_save(self._path, {"version": _VERSION, "images": images})
        self._images = images

    def path_for(self, ref: str) -> Optional[str]:
        entry = self._images.get(ref)
        return entry["path"] if entry else None

    def owners(self, ref: str) -> list[str]:
        entry = self._images.get(ref)
        return list(entry["owners"]) if entry else []

    def refs(self) -> list[str]:
        return list(self._images)

    def remember(self, ref: str, path: str, owner: str, now: Optional[int] = None) -> list[str]:
        """Adds or refreshes a picture for `owner`; returns refs pushed out by the cap."""
        if not valid_source(ref, path) or not valid_owner(owner):
            raise ValueError("invalid_theme_image")
        previous = self._images.get(ref)
        owners = sorted({*(previous["owners"] if previous else []), owner})
        images = {**self._images, ref: {"path": path, "at": int(time.time()) if now is None else now, "owners": owners}}
        images, evicted = self._bounded(images)
        self._save(images)
        return evicted

    def keep(self, owner: str, refs: set[str], adopt: Optional[dict[str, str]] = None, now: Optional[int] = None) -> list[str]:
        """`owner` still shows exactly `refs`. Drops the owner from its other entries and returns the entries no
        theme keeps any more, plus any the cap pushed out. A listed entry joins the owner only when it has no
        owner yet or already has this one, so a theme never takes over another's picture. `adopt` maps listed
        refs the store does not have to their paths, to add them for `owner`. Writes nothing when nothing changes."""
        images = {}
        dropped = []
        for ref, entry in self._images.items():
            owners = set(entry["owners"])
            if ref in refs:
                if not owners or owner in owners:
                    owners.add(owner)
            elif owner in owners:
                owners.discard(owner)
                if not owners:
                    dropped.append(ref)
                    continue
            images[ref] = {**entry, "owners": sorted(owners)}
        at = int(time.time()) if now is None else now
        for ref, path in (adopt or {}).items():
            if ref in refs and ref not in images and valid_source(ref, path):
                images[ref] = {"path": path, "at": at, "owners": [owner]}
        images, evicted = self._bounded(images)
        if images != self._images:
            self._save(images)
        return dropped + evicted

    def __len__(self) -> int:
        return len(self._images)


def valid_owner(owner: Any) -> bool:
    return isinstance(owner, str) and 0 < len(owner) <= MAX_OWNER_LENGTH


def valid_source(ref: Any, path: Any) -> bool:
    return (
        isinstance(ref, str)
        and isinstance(path, str)
        and os.path.isabs(path)
        and os.path.normpath(path) == path
        and "\0" not in path
        and local_media_id(path) == ref
    )
