from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any, Optional

from .remote_sources import Opener, _fetch_json, default_opener

_STORE = "https://store.steampowered.com/api/appdetails?appids={appid}&filters=movies"
_ALBUMS = "https://itunes.apple.com/search?term={term}&media=music&entity=album&limit=15"
_TRACKS = "https://itunes.apple.com/lookup?id={album}&entity=song&limit=8"
_SOUNDTRACK = re.compile(r"\b(original|soundtrack|ost|score)\b")
# Fan covers, remixes and singles share the game's name but are not its soundtrack.
_NOT_OFFICIAL = re.compile(r"\b(cover|piano|lofi|lo fi|remix|metal|drill|inspired|epic version|arrangement|tribute|single|from)\b")
# What an official soundtrack adds to the game's name; anything else (a sequel, a DLC) is another album.
_SOUNDTRACK_WORDS = frozenset({"original", "game", "video", "soundtrack", "ost", "score", "music", "the", "deluxe", "edition", "complete", "vol", "volume", "ep", "digital", "official"})
_STEAM_VIDEO = ("https://video.akamai.steamstatic.com/", "https://video.fastly.steamstatic.com/", "https://cdn.akamai.steamstatic.com/")


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def pick_trailer(details: Any, appid: str) -> Optional[dict[str, str]]:
    """The store's highlighted trailer as HLS, which Steam now serves instead of plain mp4."""
    data = (details or {}).get(appid) if isinstance(details, dict) else None
    if not isinstance(data, dict) or not data.get("success"):
        return None
    movies = [m for m in (data.get("data") or {}).get("movies") or [] if isinstance(m, dict)]
    movies.sort(key=lambda m: not m.get("highlight"))
    for movie in movies:
        url = movie.get("hls_h264")
        if isinstance(url, str) and url.startswith(_STEAM_VIDEO):
            return {"url": url, "poster": str(movie.get("thumbnail") or ""), "title": str(movie.get("name") or "")}
    return None


def pick_album(results: Any, game: str) -> Optional[int]:
    """The official soundtrack album: named after the game, labelled as a soundtrack, not a cover."""
    wanted = _plain(game)
    if not wanted or not isinstance(results, dict):
        return None
    best: Optional[tuple[int, int]] = None
    for album in results.get("results") or []:
        if not isinstance(album, dict) or not isinstance(album.get("collectionId"), int):
            continue
        name = _plain(str(album.get("collectionName") or ""))
        if not name.startswith(wanted) or not _SOUNDTRACK.search(name) or _NOT_OFFICIAL.search(name):
            continue
        rest = name[len(wanted):].split()
        # A number only belongs to a volume ("Vol. 2"); right after the name it is a sequel.
        if any(word not in _SOUNDTRACK_WORDS and not (word.isdigit() and i > 0 and rest[i - 1] in ("vol", "volume")) for i, word in enumerate(rest)):
            continue
        score = len(rest)
        if best is None or score < best[0]:
            best = (score, album["collectionId"])
    return best[1] if best else None


def pick_track(lookup: Any) -> Optional[dict[str, str]]:
    for track in (lookup or {}).get("results") or [] if isinstance(lookup, dict) else []:
        if isinstance(track, dict) and track.get("wrapperType") == "track":
            url = track.get("previewUrl")
            if isinstance(url, str) and url.startswith("https://"):
                return {"url": url, "title": str(track.get("trackName") or ""), "artist": str(track.get("artistName") or "")}
    return None


def game_trailer(appid: str, opener: Opener = default_opener) -> Optional[dict[str, str]]:
    if not appid.isdigit():
        return None
    return pick_trailer(_fetch_json(_STORE.format(appid=appid), opener), appid)


def game_theme(name: str, opener: Opener = default_opener) -> Optional[dict[str, str]]:
    if not name.strip():
        return None
    album = pick_album(_fetch_json(_ALBUMS.format(term=urllib.parse.quote(f"{name} soundtrack")), opener), name)
    return pick_track(_fetch_json(_TRACKS.format(album=album), opener)) if album else None
