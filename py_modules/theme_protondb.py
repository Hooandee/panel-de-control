"""ProtonDB's rating for themes. Its API only answers its own site (CORS), so Panel asks for it.

GET https://www.protondb.com/api/v1/reports/summaries/<appid>.json gives `tier` (platinum, gold, silver,
bronze, borked, pending) with `confidence` and `total` reports; a game nobody reported is a 404. Answers are kept
on disk by appid: a rating for 7 days, a miss for 2; a network failure is never kept.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from json_store import atomic_json_save

URL = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
USER_AGENT = "Panel de Control (theme ProtonDB lookup)"
TIMEOUT_S = 8
FOUND_TTL_S = 7 * 86_400
MISSING_TTL_S = 2 * 86_400
CACHE_LIMIT = 2_000
TIERS = {"platinum", "gold", "silver", "bronze", "borked", "native"}
APPID = re.compile(r"^[1-9]\d{0,9}$")

Fetch = Callable[[str], bytes]


def _default_fetch(url: str) -> bytes:
    from http_util import ssl_context

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=ssl_context()) as response:
        return response.read()


class ProtonDbLookup:
    def __init__(self, cache_path: str, fetch: Fetch = _default_fetch, clock: Callable[[], float] = time.time):
        self._path = cache_path
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None

    def _load(self) -> dict:
        if self._cache is None:
            try:
                with open(self._path) as handle:
                    data = json.load(handle)
                self._cache = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._cache = {}
        return self._cache

    def _keep(self, appid: str, answer: dict) -> None:
        cache = self._load()
        cache[appid] = {**answer, "at": self._clock()}
        if len(cache) > CACHE_LIMIT:
            for key in sorted(cache, key=lambda k: cache[k].get("at", 0))[: len(cache) - CACHE_LIMIT]:
                del cache[key]
        try:
            atomic_json_save(self._path, cache)
        except OSError:
            pass

    def lookup(self, appid) -> dict:
        appid = str(appid) if isinstance(appid, int) else appid
        # Shortcuts (non-Steam games) have ids past 2^32 and no ProtonDB page.
        if not isinstance(appid, str) or not APPID.match(appid) or int(appid) > 0xFFFFFFFF:
            return {"result": "invalid"}
        with self._lock:
            kept = self._load().get(appid)
            if isinstance(kept, dict):
                ttl = FOUND_TTL_S if kept.get("result") == "found" else MISSING_TTL_S
                if self._clock() - kept.get("at", 0) < ttl:
                    return {key: value for key, value in kept.items() if key != "at"}
            try:
                data = json.loads(self._fetch(URL.format(appid=appid)))
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    answer = {"result": "not_found"}
                    self._keep(appid, answer)
                    return answer
                return {"result": "unavailable", "code": f"http_{error.code}"}
            except Exception as error:  # noqa: BLE001
                return {"result": "unavailable", "code": type(error).__name__}
            tier = data.get("tier") if isinstance(data, dict) else None
            if tier not in TIERS:
                answer = {"result": "not_found"}
            else:
                total = data.get("total")
                answer = {
                    "result": "found",
                    "tier": tier,
                    "confidence": data.get("confidence") if isinstance(data.get("confidence"), str) else None,
                    "total": total if isinstance(total, int) and total >= 0 else None,
                }
            self._keep(appid, answer)
            return answer


def cache_path(settings_dir: str) -> str:
    return os.path.join(settings_dir, "protondb_cache.json")
