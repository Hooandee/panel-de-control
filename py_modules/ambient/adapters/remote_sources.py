from __future__ import annotations

import datetime
import errno
import json
import os
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from http_util import ssl_context
from version import read_version

from ..core.cache_policy import cache_filename

Opener = Callable[[urllib.request.Request, float], Any]

TIMEOUT_SEC = 15.0
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MAX_PLAYLIST_BYTES = 8 * 1024 * 1024
MAX_TRANSFER_SEC = 600
NASA_DAYS = 8


class RemoteError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": f"PanelDeControl/{read_version()}"})


def _fetch_json(url: str, opener: Opener) -> Any:
    try:
        with opener(build_request(url), TIMEOUT_SEC) as response:
            return json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except (OSError, ValueError):
        return None


def _nasa_library_images(opener: Opener) -> list[dict[str, str]]:
    query = urllib.parse.urlencode({"q": "nebula", "media_type": "image", "page_size": NASA_DAYS})
    data = _fetch_json(f"https://images-api.nasa.gov/search?{query}", opener)
    collection = data.get("collection") if isinstance(data, dict) else None
    entries = collection.get("items") if isinstance(collection, dict) else None
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        metadata, links = entry.get("data"), entry.get("links")
        if not isinstance(metadata, list) or not isinstance(links, list):
            continue
        info = next((row for row in metadata if isinstance(row, dict) and row.get("media_type") == "image"), None)
        if info is None:
            continue
        images = [link for link in links if isinstance(link, dict) and link.get("render") == "image"
                  and isinstance(link.get("href"), str) and link["href"].startswith("https://images-assets.nasa.gov/")]
        if not images:
            continue
        def width(link: dict[str, Any]) -> int:
            value = link.get("width")
            return value if isinstance(value, int) and value > 0 else 0
        screen_images = [link for link in images if 0 < width(link) <= 1920]
        image = max(screen_images or images, key=width)
        url = image["href"]
        if url in seen:
            continue
        seen.add(url)
        credit = info.get("secondary_creator") or info.get("photographer") or ("NASA/" + str(info["center"]) if info.get("center") else "NASA")
        items.append({"url": url, "title": str(info.get("title", "NASA"))[:120], "credit": str(credit).strip()[:120]})
        if len(items) >= NASA_DAYS:
            break
    return items


def nasa_images(opener: Opener = default_opener, today: Optional[str] = None,
                on_fallback: Optional[Callable[[], None]] = None) -> list[dict[str, str]]:
    end = datetime.date.fromisoformat(today) if today else datetime.date.today()
    start = end - datetime.timedelta(days=NASA_DAYS - 1)
    query = urllib.parse.urlencode({"api_key": "DEMO_KEY", "start_date": start.isoformat(), "thumbs": "false"})
    data = _fetch_json(f"https://api.nasa.gov/planetary/apod?{query}", opener)
    entries = data if isinstance(data, list) else []
    items = []
    for entry in sorted((e for e in entries if isinstance(e, dict)), key=lambda e: str(e.get("date", "")), reverse=True):
        url = entry.get("hdurl") or entry.get("url")
        if entry.get("media_type") != "image" or not isinstance(url, str) or not url.startswith("https://"):
            continue
        # APOD can return NASA Science's generic page logo when its article is unavailable.
        if url.split("?", 1)[0] == "https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png":
            continue
        items.append({"url": url, "title": str(entry.get("title", ""))[:120], "credit": str(entry.get("copyright", "NASA")).strip()[:120]})
    if items:
        return items[:NASA_DAYS]
    if on_fallback:
        on_fallback()
    items = _nasa_library_images(opener)
    if not items:
        raise RemoteError("nasa_unavailable")
    return items


def bing_images(opener: Opener = default_opener, market: str = "en-US") -> list[dict[str, str]]:
    query = urllib.parse.urlencode({"format": "js", "idx": 0, "n": 8, "mkt": market})
    data = _fetch_json(f"https://www.bing.com/HPImageArchive.aspx?{query}", opener)
    images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(images, list):
        return []
    items = []
    for entry in images:
        path = entry.get("url") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        items.append({"url": "https://www.bing.com" + path, "title": str(entry.get("title", ""))[:120], "credit": str(entry.get("copyright", ""))[:160]})
    return items


def download(url: str, cache_dir: str, opener: Opener = default_opener, max_bytes: Optional[int] = None) -> str:
    if not url.startswith(("https://", "http://")):
        raise RemoteError("invalid_url")
    try:
        response_cm = opener(build_request(url), TIMEOUT_SEC)
    except OSError as exc:
        raise RemoteError("unreachable") from exc
    with response_cm as response:
        mime = str(response.headers.get("Content-Type", "")).split(";")[0].strip().lower()
        name = cache_filename(url, mime)
        if name is None:
            raise RemoteError("unsupported_type")
        limit = max_bytes if max_bytes is not None else (MAX_VIDEO_BYTES if mime.startswith("video/") else MAX_IMAGE_BYTES)
        tmp = None
        try:
            os.makedirs(cache_dir, exist_ok=True)
            try:
                length = int(response.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                length = 0
            if length > limit:
                raise RemoteError("too_large")
            if length > 0 and length > shutil.disk_usage(cache_dir).free:
                raise RemoteError("no_space")
            fd, tmp = tempfile.mkstemp(prefix=".dl.", suffix=".tmp", dir=cache_dir)
            total = 0
            started = time.monotonic()
            with os.fdopen(fd, "wb") as out:
                while True:
                    if time.monotonic() - started > MAX_TRANSFER_SEC:
                        raise RemoteError("timeout")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise RemoteError("too_large")
                    out.write(chunk)
            target = os.path.join(cache_dir, name)
            os.replace(tmp, target)
            return target
        except OSError as exc:
            reason = "no_space" if exc.errno in (errno.ENOSPC, errno.EDQUOT) else "transfer_failed"
            raise RemoteError(reason) from exc
        finally:
            if tmp is not None and os.path.exists(tmp):
                os.unlink(tmp)


def fetch_text(url: str, opener: Opener = default_opener, limit: int = MAX_PLAYLIST_BYTES) -> str:
    """Small text resources such as M3U playlists; refuses anything past `limit` bytes."""
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("unsupported_url")
    with opener(build_request(url), TIMEOUT_SEC) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("playlist_too_large")
    return data.decode("utf-8", errors="replace")
