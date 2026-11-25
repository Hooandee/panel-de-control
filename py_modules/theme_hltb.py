"""How Long to Beat for themes. Steam's client cannot reach howlongtobeat.com (CORS), so Panel asks for it.

The site's own search (2026-11): GET /api/search/site/init gives a token, POST /api/search/site with that
token in `x-auth-token` searches by words. Results carry seconds (`comp_main`, `comp_plus`, `comp_100`) but no
Steam appid, so the game is matched by its normalised name. Answers are kept on disk by appid: a found game for
30 days, a miss for 3; a network failure is never kept. One lookup at a time, and the token is reused until
the site refuses it.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Callable, Optional

from json_store import atomic_json_save

BASE = "https://howlongtobeat.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT_S = 8
FOUND_TTL_S = 30 * 86_400
MISSING_TTL_S = 3 * 86_400
CACHE_LIMIT = 2_000
MATCH_THRESHOLD = 0.82
APPID = re.compile(r"^[1-9]\d{0,19}$")

# Words Steam puts in a store name that HLTB leaves out.
EDITION = re.compile(
    r"\b(game of the year|goty|definitive|complete|deluxe|ultimate|enhanced|anniversary|director'?s cut|"
    r"remastered|remaster|edition|special|gold|premium|legendary|royal|hd)\b"
)

Fetch = Callable[[str, Optional[bytes], dict], bytes]


def normalise(name: str) -> str:
    # NFKD would spell ™ out as "TM".
    text = re.sub("[\u2122\u00ae\u00a9]", " ", name)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = EDITION.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def best_match(name: str, results: list) -> Optional[dict]:
    wanted = normalise(name)
    if not wanted:
        return None
    best: Optional[dict] = None
    best_score = 0.0
    for entry in results:
        if not isinstance(entry, dict):
            continue
        names = [entry.get("game_name"), *str(entry.get("game_alias") or "").split(",")]
        for candidate in names:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            have = normalise(candidate)
            if not have:
                continue
            score = 1.0 if have == wanted else SequenceMatcher(None, wanted, have).ratio()
            # "The Witcher 3 Wild Hunt" for "The Witcher 3: Wild Hunt — Remastered" once editions are gone.
            if score < 1.0 and (wanted.startswith(have) or have.startswith(wanted)):
                score = max(score, 0.9)
            if score > best_score:
                best, best_score = entry, score
    return best if best_score >= MATCH_THRESHOLD else None


def hours(seconds) -> Optional[float]:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    return round(seconds / 3600, 1)


def _default_fetch(url: str, body: Optional[bytes], headers: dict) -> bytes:
    from http_util import ssl_context

    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=ssl_context()) as response:
        return response.read()


class Unavailable(Exception):
    pass


class HltbLookup:
    def __init__(self, cache_path: str, fetch: Fetch = _default_fetch, clock: Callable[[], float] = time.time):
        self._path = cache_path
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._token: Optional[str] = None
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

    def _save(self) -> None:
        cache = self._load()
        if len(cache) > CACHE_LIMIT:
            for key in sorted(cache, key=lambda k: cache[k].get("at", 0))[: len(cache) - CACHE_LIMIT]:
                del cache[key]
        try:
            atomic_json_save(self._path, cache)
        except OSError:
            pass

    def _headers(self) -> dict:
        return {"User-Agent": USER_AGENT, "Referer": f"{BASE}/", "Origin": BASE}

    def _new_token(self) -> str:
        try:
            raw = self._fetch(f"{BASE}/api/search/site/init?t={int(self._clock() * 1000)}", None, self._headers())
            token = json.loads(raw).get("token")
        except Exception as error:  # noqa: BLE001
            raise Unavailable(type(error).__name__) from error
        if not isinstance(token, str) or not token:
            raise Unavailable("no_token")
        return token

    def _search(self, name: str) -> list:
        body = json.dumps({
            "searchType": "games",
            "searchTerms": normalise(name).split(" ") or [name],
            "searchPage": 1,
            "size": 20,
            "searchOptions": {
                "games": {
                    "userId": 0, "platform": "", "sortCategory": "popular", "rangeCategory": "main",
                    "rangeTime": {"min": 0, "max": 0}, "gameplay": {"perspective": "", "flow": "", "genre": ""},
                    "year": "", "modifier": "",
                },
                "users": {"sortCategory": "postcount"},
                "lists": {"sortCategory": "follows"},
                "filter": "", "sort": 0, "randomizer": 0,
            },
            "useCache": True,
        }).encode()
        for attempt in range(2):
            if self._token is None:
                self._token = self._new_token()
            headers = {**self._headers(), "Content-Type": "application/json", "x-auth-token": self._token}
            try:
                data = json.loads(self._fetch(f"{BASE}/api/search/site", body, headers))
            except urllib.error.HTTPError as error:
                # An expired token is refused with 403: one fresh token, once.
                if error.code in (401, 403) and attempt == 0:
                    self._token = None
                    continue
                raise Unavailable(f"http_{error.code}") from error
            except Exception as error:  # noqa: BLE001
                raise Unavailable(type(error).__name__) from error
            results = data.get("data") if isinstance(data, dict) else None
            return results if isinstance(results, list) else []
        raise Unavailable("token_refused")

    def lookup(self, appid, name) -> dict:
        appid = str(appid) if isinstance(appid, int) else appid
        if not isinstance(appid, str) or not APPID.match(appid) or not isinstance(name, str) or not name.strip():
            return {"result": "invalid"}
        name = name.strip()[:200]
        with self._lock:
            cache = self._load()
            now = self._clock()
            kept = cache.get(appid)
            if isinstance(kept, dict) and kept.get("name") == name:
                ttl = FOUND_TTL_S if kept.get("result") == "found" else MISSING_TTL_S
                if now - kept.get("at", 0) < ttl:
                    return {key: value for key, value in kept.items() if key not in ("at", "name")}
            try:
                match = best_match(name, self._search(name))
            except Unavailable as error:
                return {"result": "unavailable", "code": str(error)}
            if match is None:
                answer = {"result": "not_found"}
            else:
                answer = {
                    "result": "found",
                    "main": hours(match.get("comp_main")),
                    "plus": hours(match.get("comp_plus")),
                    "complete": hours(match.get("comp_100")),
                    "title": match.get("game_name") if isinstance(match.get("game_name"), str) else None,
                    "id": match.get("game_id") if isinstance(match.get("game_id"), int) else None,
                }
            cache[appid] = {**answer, "name": name, "at": now}
            self._save()
            return answer


def cache_path(settings_dir: str) -> str:
    return os.path.join(settings_dir, "hltb_cache.json")
