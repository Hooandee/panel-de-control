"""Which real game a non-Steam executable is, so Steam recipes and wiki notes apply to it too.

Evidence, strongest first: a Steam appid left in the folder by the release, the executable's own
product name, then the shortcut and folder names cleaned of release tags, looked up in Steam's
store search. Only the cleaned game name ever leaves the device.
"""

import difflib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from http_util import ssl_context

from . import pe

APPID_FILES = ("steam_appid.txt", "steam_settings/steam_appid.txt")
APPID_INI = re.compile(r"(?im)^\s*(?:real)?app_?id\s*=\s*(\d{3,9})\s*$")
INI_LIMIT = 64 * 1024
SEARCH_URL = "https://store.steampowered.com/api/storesearch/?l=english&cc=US&term="
SEARCH_TIMEOUT_S = 6
MATCH_RATIO = 0.6

_BRACKETS = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")
_RELEASE_TAGS = re.compile(
    r"\b(?:fitgirl|dodi|elamigos|kaos|xatab|codex|skidrow|plaza|empress|rune|tenoke|flt|razor1911|"
    r"cpy|hoodlum|reloaded|prophet|darksiders|gog|repack|multi\d*|eng|portable|cracked|crack|"
    r"build\s*\d+|update\s*\d+|v\d+(?:[._]\d+)*[a-z]?|\d+(?:\.\d+){2,})\b",
    re.I,
)
_SEPARATORS = re.compile(r"[_.\-+]+")
_SPACES = re.compile(r"\s+")


def clean_name(text: str) -> str:
    text = _BRACKETS.sub(" ", text or "")
    # Versions keep their dots until they are gone; tags glued with "_" only split after.
    text = _RELEASE_TAGS.sub(" ", text)
    text = _SEPARATORS.sub(" ", text)
    text = _RELEASE_TAGS.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def appid_from_files(root: Path, exe_dir: Path | None) -> tuple[int | None, str | None]:
    folders = [p for p in dict.fromkeys([exe_dir, root]) if p]
    for folder in folders:
        for relative in APPID_FILES:
            try:
                value = (folder / relative).read_text(errors="replace").strip().split()[0]
            except (OSError, IndexError):
                continue
            if value.isdecimal():
                return int(value), relative
        try:
            inis = [p for p in folder.iterdir() if p.suffix.lower() == ".ini"]
        except OSError:
            continue
        for ini in inis:
            try:
                if ini.stat().st_size > INI_LIMIT:
                    continue
                match = APPID_INI.search(ini.read_text(errors="replace"))
            except OSError:
                continue
            if match:
                return int(match.group(1)), ini.name
    return None, None


def name_candidates(shortcut_name: str | None, root: Path, exe: Path | None) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if exe and exe.is_file():
        strings = pe.version_strings(str(exe))
        for key in ("ProductName", "FileDescription"):
            value = clean_name(strings.get(key, ""))
            if value and _normal(value) not in ("", "launcher", "game", "unrealengine", "bootstrap"):
                found.append((value, key))
    for value, source in ((shortcut_name, "shortcut"), (root.name, "folder"), (exe.stem if exe else None, "exe")):
        cleaned = clean_name(value or "")
        if cleaned and len(_normal(cleaned)) >= 3:
            found.append((cleaned, source))
    unique: dict[str, tuple[str, str]] = {}
    for value, source in found:
        unique.setdefault(_normal(value), (value, source))
    return list(unique.values())


def store_search(term: str, opener=urllib.request.urlopen) -> list[dict]:
    request = urllib.request.Request(SEARCH_URL + urllib.parse.quote(term), headers={"User-Agent": "panel-de-control"})
    try:
        with opener(request, timeout=SEARCH_TIMEOUT_S, context=ssl_context()) as response:
            data = json.loads(response.read(512 * 1024).decode("utf-8", "replace"))
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return [{"id": int(i["id"]), "name": str(i.get("name", ""))} for i in items or [] if isinstance(i, dict) and str(i.get("id", "")).isdecimal()]


def best_match(term: str, items: list[dict]) -> dict | None:
    scored = [(difflib.SequenceMatcher(None, _normal(term), _normal(i["name"])).ratio(), i) for i in items]
    scored.sort(key=lambda pair: -pair[0])
    return scored[0][1] if scored and scored[0][0] >= MATCH_RATIO else None


def identify(shortcut_name: str | None, root: Path, exe: Path | None, search=store_search) -> dict:
    appid, source = appid_from_files(root, exe.parent if exe else None)
    candidates = name_candidates(shortcut_name, root, exe)
    if appid:
        return {"steam_appid": appid, "name": candidates[0][0] if candidates else None, "source": source}
    for name, origin in candidates[:3]:
        match = best_match(name, search(name))
        if match:
            return {"steam_appid": match["id"], "name": match["name"], "source": f"store:{origin}", "query": name}
    return {"steam_appid": None, "name": candidates[0][0] if candidates else shortcut_name, "source": "unknown"}


def from_override(appid: int, name: str) -> dict:
    return {"steam_appid": appid, "name": name, "source": "user"}

