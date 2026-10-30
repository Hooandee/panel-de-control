from __future__ import annotations

import errno
import json
import os
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Literal, Optional

from json_store import atomic_json_save

from .adapters import radio_browser, remote_sources
from .adapters.game_audio import GameAudio
from .adapters.generated_cache import GeneratedCache
from .adapters.installed_games import snapshot as installed_snapshot
from .adapters.game_media import game_theme, game_trailer
from .adapters.known_paths import known_folders
from .adapters.library_scan import media_id as local_media_id, scan_folder
from .adapters.media_server import MediaServer
from .adapters.optimizer import OptimizeError, optimize, output_name
from .adapters.remote_sources import download
from .adapters.steam_screenshots import screenshot_folders
from .core import collections as coll
from .core.m3u import parse_m3u
from .core.path_guard import resolve_servable
from .core.settings import default_settings, normalize_settings

FolderScope = Literal["background", "music", "library"]
ItemScope = Literal["background", "radio", "music", "library"]

_VISUAL = {"image", "video"}
_MAX_EVENTS = 20
DISCOVER_TTL_SEC = 600
PLAYLIST_TTL_SEC = 6 * 3600
DISCOVER_CACHE_SIZE = 64
_EVENT_KINDS = {"playback_error", "radio_error", "conflict", "power", "serve_error", "remote_error", "cache", "video_fullscreen"}


_GAME_MEDIA_TTL_S = 7 * 24 * 3600
_GAME_MEDIA_MISS_TTL_S = 24 * 3600
_GAME_MEDIA_MAX = 300


class AmbientService:
    """Ambient domain use cases. Blocking by design: callers run it off the event loop."""

    def __init__(self, state_dir: str, cache_dir: str, home: str):
        self._settings_path = os.path.join(state_dir, "settings.json")
        self._game_audio = GameAudio()
        self._game_media_path = os.path.join(cache_dir, "game-media.json")
        self._game_media: Optional[dict[str, Any]] = None
        self._cache_dir = cache_dir
        self._cache_index_path = os.path.join(cache_dir, "index.json")
        self._home = home
        self._generated = GeneratedCache(cache_dir)
        self._installed_path = os.path.join(cache_dir, "installed-games.json")
        self._lock = threading.RLock()
        self._settings = self._load_settings()
        assigned = self._explicit_refs(self._settings)
        self._game_sources = {ref: path for ref, path in self._read_cache_index()["sources"].items() if ref in assigned and self._valid_game_source(ref, path)}
        self._index: dict[str, str] = self._retained_generated()
        self._roots: list[str] = []
        self._events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
        self._discover_cache: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._playlist_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._server = MediaServer(resolver=self._resolve)
        self._server_started = False
        self._server_lock = threading.Lock()
        self._closed = False
        self._cancel = threading.Event()

    def close(self) -> None:
        self._closed = True
        self._cancel.set()
        with self._server_lock:
            self._server.stop()
            self._server_started = False

    def cancel_jobs(self) -> None:
        """Stops a running optimization (e.g. a game started); later jobs start fresh."""
        self._cancel.set()
        self._cancel = threading.Event()


    def _load_settings(self) -> dict[str, Any]:
        try:
            with open(self._settings_path, encoding="utf-8") as handle:
                return normalize_settings(json.load(handle))
        except (OSError, ValueError):
            return default_settings()

    def _commit(self, settings: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            normalized = normalize_settings(settings)
            references_changed = (
                self._settings["collections"] != normalized["collections"]
                or self._settings["music"]["folders"] != normalized["music"]["folders"]
                or self._settings["radio"]["favorites"] != normalized["radio"]["favorites"]
                or self._settings["background"]["perGame"] != normalized["background"]["perGame"]
                or self._settings["background"]["selectedRefs"] != normalized["background"]["selectedRefs"]
            )
            sources = {}
            for ref in self._explicit_refs(normalized):
                path = self._index.get(ref) or self._game_sources.get(ref)
                if self._valid_game_source(ref, path):
                    sources[ref] = path
            retained = self._game_sources | sources
            if retained != self._game_sources:
                self._save_game_sources(retained)
            atomic_json_save(self._settings_path, normalized)
            self._settings = normalized
            self._game_sources = sources
            if retained != sources:
                try:
                    self._save_game_sources(sources)
                except OSError:
                    pass
            if references_changed:
                self._prune_generated()
            return self._settings

    def save_settings(self, raw: Any) -> dict[str, Any]:
        return self._commit(raw)

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            settings = json.loads(json.dumps(self._settings))
        known = known_folders(self._home)
        extra: list[dict[str, str]] = []
        if known["images"] or known["videos"]:
            extra.append({"id": "known.images", "kind": "known"})
        if known["music"]:
            extra.append({"id": "known.music", "kind": "known"})
        if screenshot_folders(self._home):
            extra.append({"id": "screenshots", "kind": "screenshots"})
        return {
            "settings": settings,
            "knownFolders": known,
            "collections": extra + self._library_collections(settings),
            "mediaServer": self._server_state(),
        }


    @staticmethod
    def _library_folders(settings: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(settings["collections"]["folders"] + settings["music"]["folders"]))

    @classmethod
    def _library_collections(cls, settings: dict[str, Any]) -> list[dict[str, str]]:
        entries = coll.visible_backgrounds(settings)
        ids = {entry["id"] for entry in entries}
        for path in cls._library_folders(settings):
            key = coll.stable_id("folder", path)
            if key not in ids:
                entries.append({"id": key, "kind": "folder", "name": os.path.basename(path.rstrip("/")) or path, "path": path})
                ids.add(key)
        urls = {entry["url"] for entry in entries if "url" in entry}
        for favorite in settings["radio"]["favorites"]:
            if favorite["url"] not in urls:
                entries.append({"id": favorite["id"], "kind": "favorite", "name": favorite["name"], "url": favorite["url"]})
                urls.add(favorite["url"])
        return entries

    def add_folder(self, path: str, scope: FolderScope = "background") -> dict[str, Any]:
        real = os.path.realpath(path)
        if not os.path.isdir(real):
            raise ValueError("not_a_directory")
        with self._lock:
            settings = json.loads(json.dumps(self._settings))
        folders = settings["music" if scope == "music" else "collections"]["folders"]
        if real not in folders:
            folders.append(real)
        return self._commit(settings)

    def add_favorite(self, scope: coll.Scope, url: str, name: str, art: str = "", subtitle: str = "") -> dict[str, Any]:
        with self._lock:
            return self._commit(coll.add_favorite(self._settings, scope, url, name, art, subtitle))

    def remove_item(self, scope: ItemScope, item_id: str) -> dict[str, Any]:
        with self._lock:
            settings = self._settings
            if scope == "library":
                settings = json.loads(json.dumps(settings))
                removed_ids = {item_id}
                removed_folders = [path for path in self._library_folders(settings) if item_id in (path, coll.stable_id("folder", path))]
                for store in ("collections", "music"):
                    for path in settings[store]["folders"]:
                        if item_id in (path, coll.stable_id("folder", path)):
                            removed_ids.add(coll.stable_id("folder", path))
                    settings[store]["folders"] = [path for path in settings[store]["folders"] if coll.stable_id("folder", path) not in removed_ids]
                favorites = settings["collections"]["favorites"] + settings["radio"]["favorites"]
                removed_urls = {favorite["url"] for favorite in favorites if favorite["id"] == item_id}
                removed_ids.update(favorite["id"] for favorite in favorites if favorite["url"] in removed_urls)
                for store in ("collections", "radio"):
                    settings[store]["favorites"] = [favorite for favorite in settings[store]["favorites"] if favorite["url"] not in removed_urls]
                settings["background"]["collections"] = [key for key in settings["background"]["collections"] if key not in removed_ids]
                self._clear_removed_pin(settings, removed_folders, removed_urls)
                return self._commit(coll.remove_item(settings, "background", item_id))
            if scope == "music":
                settings = json.loads(json.dumps(settings))
                settings["music"]["folders"] = [f for f in settings["music"]["folders"] if item_id not in (f, coll.stable_id("folder", f))]
                return self._commit(settings)
            removed = coll.remove_item(settings, scope, item_id)
            if scope == "background":
                folders = [path for path in self._library_folders(settings) if coll.stable_id("folder", path) == item_id]
                urls = {favorite["url"] for favorite in settings["collections"]["favorites"] if favorite["id"] == item_id}
                self._clear_removed_pin(removed, folders, urls, {item_id})
            return self._commit(removed)

    def _clear_removed_pin(self, settings: dict[str, Any], folders: list[str], urls: set[str], collections: set[str] | None = None) -> None:
        pinned = settings["background"]["pinned"]
        if not pinned:
            return
        if pinned.startswith("remote:"):
            remaining = settings["collections"]["favorites"] + settings["radio"]["favorites"]
            owners = {owner for record in self._generated.records.values() if record["ref"] == pinned for owner in record["collections"]}
            visible = {entry["id"] for entry in self._library_collections(settings)}
            was_removed = pinned[7:] in urls or bool(owners & (collections or set()))
            if was_removed and not owners & visible and not any(favorite["url"] == pinned[7:] for favorite in remaining):
                settings["background"]["pinned"] = ""
            return
        source = self._index.get(pinned) or next((record["source"] for record in self._generated.records.values() if record["ref"] == pinned), "")
        if any(self._inside(source, folder) for folder in folders):
            if not self._source_collections(source) and not any(self._inside(source, folder) for folder in self._library_folders(settings)):
                settings["background"]["pinned"] = ""

    def restore_suggested(self, scope: coll.Scope, item_id: str = "") -> dict[str, Any]:
        with self._lock:
            return self._commit(coll.restore_suggested(self._settings, scope, item_id))

    def scan(self) -> dict[str, Any]:
        with self._lock:
            settings = self._settings
        known = known_folders(self._home)
        index: dict[str, str] = {}
        roots: list[str] = []
        truncated = False

        def collect(folders: list[str], kinds: set[str], depth: int = 3) -> list[dict[str, Any]]:
            nonlocal truncated
            items: dict[str, dict[str, Any]] = {}
            for folder in dict.fromkeys(folders):
                result = scan_folder(folder, kinds=kinds, max_depth=depth)
                truncated = truncated or result.truncated
                if result.missing:
                    continue
                roots.append(folder)
                for item in result.items:
                    index[item["id"]] = item["path"]
                    items[item["id"]] = {k: item[k] for k in ("id", "name", "kind", "size", "mtime")}
            return list(items.values())

        kinds = _VISUAL | {"audio"}
        library = {
            "known.images": collect(known["images"] + known["videos"], kinds),
            "known.music": collect(known["music"], kinds),
        }
        shots = screenshot_folders(self._home)
        if shots:
            library["screenshots"] = collect(shots, {"image"}, depth=0)
        for folder in self._library_folders(settings):
            library[coll.stable_id("folder", folder)] = collect([folder], kinds)
        collections = {key: [item for item in items if item["kind"] in _VISUAL] for key, items in library.items()}
        music = {item["id"]: item for items in [library["known.music"], *library.values()] for item in items if item["kind"] == "audio"}
        with self._lock:
            index.update(self._retained_generated())
            self._index = index
            self._roots = roots + [self._cache_dir]
        return {"collections": collections, "music": list(music.values()), "library": library, "truncated": truncated}


    @staticmethod
    def _explicit_refs(settings: dict[str, Any]) -> set[str]:
        background = settings["background"]
        return set(background["perGame"].values()) | set(background["selectedRefs"])

    @staticmethod
    def _valid_game_source(ref: str, path: Any) -> bool:
        return isinstance(path, str) and os.path.isabs(path) and os.path.normpath(path) == path and "\0" not in path and local_media_id(path) == ref

    def _save_game_sources(self, sources: dict[str, str]) -> None:
        data = self._read_cache_index()
        data["sources"] = sources
        try:
            atomic_json_save(self._cache_index_path, data)
        except OSError as error:
            self.record_event("cache", "sources:" + ("no_space" if error.errno in {errno.ENOSPC, errno.EDQUOT} else "write_failed"))
            raise

    def _retained_generated(self) -> dict[str, str]:
        retained = {}
        for name, record in self._generated.records.items():
            path = self._generated._target(name)
            if path and os.path.isfile(path) and self._owners(record["ref"], record["source"], record["collections"]):
                prefix = "opt:" if name.startswith("optimized/") else "url:"
                retained[prefix + os.path.splitext(os.path.basename(name))[0]] = path
        return retained

    def _resolve(self, media_id: str) -> Optional[str]:
        with self._lock:
            path = self._index.get(media_id)
            roots = list(self._roots) or [self._cache_dir]
            assigned = self._game_sources.get(media_id) if media_id in self._explicit_refs(self._settings) else None
        if assigned:
            if os.path.realpath(assigned) != assigned or os.path.islink(assigned):
                return None
            return resolve_servable(assigned, [os.path.dirname(assigned)])
        return resolve_servable(path, roots) if path else None

    def _ensure_server(self) -> bool:
        with self._server_lock:
            if self._closed:
                return False
            if not self._server_started:
                self._server.start()
                self._server_started = True
            return True

    def _server_state(self) -> str:
        return "loopback" if self._server_started else "stopped"

    def media_url(self, media_id: str) -> Optional[str]:
        if self._resolve(media_id) is None or not self._ensure_server():
            return None
        return self._server.url_for(media_id)

    def game_media(self, appid: str, name: str, now: Optional[float] = None, store: bool = True) -> dict[str, Any]:
        """Official trailer and a soundtrack preview for a game; found once, remembered for a week."""
        now = time.time() if now is None else now
        with self._lock:
            if self._game_media is None:
                try:
                    with open(self._game_media_path, encoding="utf-8") as handle:
                        loaded = json.load(handle)
                    self._game_media = loaded if isinstance(loaded, dict) else {}
                except (OSError, ValueError):
                    self._game_media = {}
            cached = self._game_media.get(appid)
        if isinstance(cached, dict) and now - cached.get("at", 0) < (_GAME_MEDIA_TTL_S if cached.get("trailer") or cached.get("theme") else _GAME_MEDIA_MISS_TTL_S):
            return {"trailer": cached.get("trailer"), "theme": cached.get("theme")}
        # A non-Steam shortcut has no store page; only its name can find a soundtrack.
        entry = {"trailer": game_trailer(appid) if store else None, "theme": game_theme(name), "at": now}
        with self._lock:
            self._game_media[appid] = entry
            if len(self._game_media) > _GAME_MEDIA_MAX:
                oldest = sorted(self._game_media, key=lambda k: self._game_media[k].get("at", 0))
                for key in oldest[: len(self._game_media) - _GAME_MEDIA_MAX]:
                    del self._game_media[key]
            try:
                os.makedirs(self._cache_dir, exist_ok=True)
                atomic_json_save(self._game_media_path, self._game_media)
            except OSError:
                pass
        return {"trailer": entry["trailer"], "theme": entry["theme"]}

    def set_game_volume(self, percent: int) -> dict[str, Any]:
        return self._game_audio.set_level(percent)

    def video_page_url(self) -> Optional[str]:
        if not self._ensure_server():
            return None
        return self._server.video_page_url()

    def _cached_path(self, url: str) -> Optional[str]:
        name = self._read_cache_index().get("urls", {}).get(url)
        if not isinstance(name, str) or "/" in name:
            return None
        path = os.path.join(self._cache_dir, name)
        return path if os.path.isfile(path) else None

    def cache_remote(self, url: str, collection: str = "") -> dict[str, Any]:
        ref = "remote:" + url
        with self._lock:
            collections = [collection] if collection in {e["id"] for e in self._library_collections(self._settings)} else []
            managed = self._owners(ref, "", collections)
            if collection and not managed:
                return {"error": "unused_media"}
        path = self._cached_path(url)
        created = path is None
        if path is None:
            path = self._download(url)
            try:
                self._remember_url(url, os.path.basename(path))
            except OSError as error:
                if error.errno in {errno.ENOSPC, errno.EDQUOT}:
                    os.unlink(path)
                    self.record_event("remote_error", "no_space")
                    return {"error": "no_space"}
                raise
        media_id = "url:" + os.path.splitext(os.path.basename(path))[0]
        with self._lock:
            self._index[media_id] = path
            if self._cache_dir not in self._roots:
                self._roots.append(self._cache_dir)
        with self._lock:
            try:
                self._generated.register(path, {"ref": ref, "source": "", "collections": collections, "managed": managed})
            except OSError as error:
                if created:
                    self._generated.discard_unregistered(path)
                self.record_event("cache", "register:" + ("no_space" if error.errno in {errno.ENOSPC, errno.EDQUOT} else "write_failed"))
                return {"error": "no_space" if error.errno in {errno.ENOSPC, errno.EDQUOT} else "cache_write_failed"}
            if path in self._prune_generated():
                return {"error": "unused_media"}
        return {"id": media_id, "url": self.media_url(media_id)}

    def _download(self, url: str) -> str:
        try:
            return download(url, self._cache_dir)
        except remote_sources.RemoteError as exc:
            self.record_event("remote_error", exc.reason)
            raise

    def _read_cache_index(self) -> dict[str, Any]:
        try:
            with open(self._cache_index_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {"used": {}, "urls": {}, "sources": {}}
        if not isinstance(data, dict):
            return {"used": {}, "urls": {}, "sources": {}}
        used = data.get("used") if isinstance(data.get("used"), dict) else {}
        urls = data.get("urls") if isinstance(data.get("urls"), dict) else {}
        sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
        return {"used": used, "urls": urls, "sources": sources}

    def _remember_url(self, url: str, name: str) -> None:
        with self._lock:
            data = self._read_cache_index()
            data["urls"][url] = name
            atomic_json_save(self._cache_index_path, data)

    def _owners(self, ref: str, source: str, collections: list[str]) -> bool:
        settings = self._settings
        if ref in self._explicit_refs(settings):
            return True
        visible = {entry["id"] for entry in self._library_collections(settings)}
        if any(owner in visible or owner in {"known.images", "known.music", "screenshots"} for owner in collections):
            return True
        if ref.startswith("remote:"):
            return any(f["url"] == ref[7:] for f in settings["collections"]["favorites"] + settings["radio"]["favorites"])
        return any(self._inside(source, folder) for folder in self._library_folders(settings))

    @staticmethod
    def _inside(path: str, folder: str) -> bool:
        return bool(path) and os.path.commonpath((os.path.abspath(path), os.path.abspath(folder))) == os.path.abspath(folder)

    def _source_collections(self, source: str) -> list[str]:
        known = known_folders(self._home)
        owners = []
        if any(self._inside(source, folder) for folder in known["images"] + known["videos"]):
            owners.append("known.images")
        if any(self._inside(source, folder) for folder in known["music"]):
            owners.append("known.music")
        if any(self._inside(source, folder) for folder in screenshot_folders(self._home)):
            owners.append("screenshots")
        return owners

    def _prune_generated(self) -> list[str]:
        try:
            removed = self._generated.prune(lambda record: self._owners(record.get("ref", ""), record.get("source", ""), record.get("collections", [])))
        except OSError as error:
            self.record_event("cache", "cleanup:" + ("no_space" if error.errno in {errno.ENOSPC, errno.EDQUOT} else "write_failed"))
            return []
        if removed:
            self._index = {ref: path for ref, path in self._index.items() if path not in removed}
            self.record_event("cache", f"removed:{len(removed)}")
        return removed

    def reconcile_games(self) -> bool:
        with self._lock:
            try:
                with open(self._installed_path, encoding="utf-8") as handle:
                    previous = json.load(handle)
                if not isinstance(previous, dict):
                    previous = {}
            except (OSError, ValueError):
                previous = {}
            current = installed_snapshot(self._home, previous.get("libraries", {}))
            if not current["complete"]:
                return False
            removed = set(previous.get("installed", [])) - set(current["installed"])
            settings = json.loads(json.dumps(self._settings))
            for appid in removed:
                settings["background"]["perGame"].pop(appid, None)
            changed = settings != self._settings
            if changed:
                self._commit(settings)
            if removed:
                self.record_event("cache", f"uninstalled:{len(removed)}")
            if current != previous:
                atomic_json_save(self._installed_path, current)
            return changed

    def optimize_media(self, media_id: str, height: int, fps: int = 30) -> dict[str, Any]:
        source = self._resolve(media_id)
        if source is None:
            return {"error": "unknown_media"}
        with self._lock:
            collections = self._source_collections(source)
            managed = self._owners(media_id, source, collections)
            if not managed:
                return {"error": "unused_media"}
        height = max(144, min(2160, int(height)))
        cache = os.path.join(self._cache_dir, "optimized")
        existed = os.path.isfile(os.path.join(cache, output_name(source, height, fps)))
        try:
            result = optimize(source, cache, height, self._cancel, fps)
        except OptimizeError as exc:
            self.record_event("serve_error", f"optimize:{exc.reason}")
            return {"error": exc.reason}
        optimized_id = "opt:" + os.path.splitext(os.path.basename(result.path))[0]
        with self._lock:
            try:
                self._generated.register(result.path, {"ref": media_id, "source": source, "collections": collections, "managed": managed})
            except OSError as error:
                if not existed:
                    self._generated.discard_unregistered(result.path)
                reason = "no_space" if error.errno in {errno.ENOSPC, errno.EDQUOT} else "cache_write_failed"
                self.record_event("cache", "register:" + reason)
                return {"error": reason}
            if result.path in self._prune_generated():
                return {"error": "unused_media"}
            self._index[optimized_id] = result.path
            if self._cache_dir not in self._roots:
                self._roots.append(self._cache_dir)
        return {"id": optimized_id, "url": self.media_url(optimized_id), "encoder": result.encoder}


    def search_radio(self, name: str = "", country: str = "", tag: str = "") -> list[dict[str, Any]]:
        stations = radio_browser.search(name=name, country=country, tag=tag)
        if not stations and (name or country or tag):
            self.record_event("radio_error", "empty_or_unreachable")
        return stations

    def suggested_stations(self) -> list[dict[str, Any]]:
        with self._lock:
            removed = set(self._settings["radio"]["removedSuggested"])
        stations: list[dict[str, Any]] = []
        for tag in coll.SUGGESTED_STATION_TAGS:
            for station in radio_browser.top(tag=tag, limit=3):
                if station["id"] not in removed and all(s["id"] != station["id"] for s in stations):
                    stations.append(station)
        return stations

    def add_playlist(self, url: str, name: str) -> dict[str, Any]:
        with self._lock:
            settings = json.loads(json.dumps(self._settings))
            playlists = settings["radio"].setdefault("playlists", [])
            if not any(p["url"] == url for p in playlists):
                playlists.append({"id": coll.stable_id("list", url), "name": name.strip() or url, "url": url})
            return self._commit(settings)

    def remove_playlist(self, playlist_id: str) -> dict[str, Any]:
        with self._lock:
            settings = json.loads(json.dumps(self._settings))
            settings["radio"]["playlists"] = [p for p in settings["radio"].get("playlists", []) if p["id"] != playlist_id]
            self._playlist_cache.pop(playlist_id, None)
            return self._commit(settings)

    def playlist(self, playlist_id: str) -> dict[str, Any]:
        """Channels of a saved playlist, from memory for six hours, then from the network, then disk."""
        with self._lock:
            entry = next((p for p in self._settings["radio"].get("playlists", []) if p["id"] == playlist_id), None)
            hit = self._playlist_cache.get(playlist_id)
        if entry is None:
            return {"id": playlist_id, "channels": [], "error": "unknown_playlist"}
        if hit and time.time() - hit[0] < PLAYLIST_TTL_SEC:
            return {"id": playlist_id, "channels": hit[1]}
        path = os.path.join(self._cache_dir, f"{playlist_id}.json")
        try:
            channels = parse_m3u(remote_sources.fetch_text(entry["url"]))
        except (OSError, ValueError) as error:
            self.record_event("playlist_error", type(error).__name__)
            try:
                with open(path, encoding="utf-8") as handle:
                    channels = json.load(handle).get("channels", [])
            except (OSError, ValueError):
                return {"id": playlist_id, "channels": [], "error": "unreachable"}
        else:
            atomic_json_save(path, {"at": time.time(), "channels": channels})
        with self._lock:
            self._playlist_cache[playlist_id] = (time.time(), channels)
        return {"id": playlist_id, "channels": channels}

    def radio_catalog(self) -> dict[str, Any]:
        """Countries and styles with station counts, cached for a day and kept on disk for offline use."""
        path = os.path.join(self._cache_dir, "radio-catalog.json")
        try:
            with open(path, encoding="utf-8") as handle:
                cached = json.load(handle)
        except (OSError, ValueError):
            cached = None
        fresh = isinstance(cached, dict) and time.time() - float(cached.get("at", 0)) < 24 * 3600
        if fresh:
            return {"countries": cached.get("countries", []), "tags": cached.get("tags", [])}
        countries, tags = radio_browser.countries(), radio_browser.tags()
        if countries or tags:
            atomic_json_save(path, {"at": time.time(), "countries": countries, "tags": tags})
            return {"countries": countries, "tags": tags}
        if isinstance(cached, dict):
            return {"countries": cached.get("countries", []), "tags": cached.get("tags", [])}
        self.record_event("radio_error", "catalog_unreachable")
        return {"countries": [], "tags": []}

    def discover_radio(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Identical queries within ten minutes are answered from memory (bounded to 64 entries)."""
        filters = filters if isinstance(filters, dict) else {}
        key = json.dumps(filters, sort_keys=True, default=str)
        now = time.time()
        with self._lock:
            hit = self._discover_cache.get(key)
            if hit and now - hit[0] < DISCOVER_TTL_SEC:
                self._discover_cache.move_to_end(key)
                return hit[1]
        stations = radio_browser.discover(filters)
        if stations:
            with self._lock:
                self._discover_cache[key] = (now, stations)
                while len(self._discover_cache) > DISCOVER_CACHE_SIZE:
                    self._discover_cache.popitem(last=False)
        return stations

    def resolve_radio(self, station_id: str) -> Optional[dict[str, Any]]:
        return radio_browser.resolve(station_id)


    def record_event(self, kind: str, detail: str) -> bool:
        if kind not in _EVENT_KINDS:
            return False
        self._events.append({"kind": kind, "detail": str(detail)[:120], "at": int(time.time())})
        return True

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            settings = self._settings
            indexed = len(self._index)
        return {
            "mediaServer": self._server_state(),
            "indexed": indexed,
            "backgroundEnabled": settings["background"]["enabled"],
            "selectedBackgroundCount": len(settings["background"]["selectedRefs"]),
            "musicEnabled": settings["music"]["enabled"],
            "musicSource": settings["music"]["source"],
            "claims": settings["claims"],
            "events": list(self._events),
        }
