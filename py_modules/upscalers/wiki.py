"""The OptiScaler wiki's compatibility table, fetched on the device and matched to a game by name.

Only facts Panel can apply or must warn about are read (the same rules as the bundled
recipes_wiki.json): -dx12, the proxy file name, REFramework, a copied nvngx_dlss.dll, anti-cheat
and games marked as not working. The note text itself is never kept.
"""

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

from http_util import ssl_context

URL = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler/Compatibility-List.md"
MAX_AGE_S = 6 * 3600
TIMEOUT_S = 8
MAX_BYTES = 4 * 1024 * 1024

_ROW = re.compile(r"^\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<status>[^|]*?)\s*\|\s*(?P<inputs>[^|]*?)\s*\|\s*(?P<patcher>[^|]*?)\s*\|\s*(?P<notes>[^|]*?)\s*\|")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_DX12 = re.compile(r"(?<![\w-])-dx12\b", re.I)
_PROXY = re.compile(r"\b(?:as|rename(?:d)? (?:it )?to|use)\s+`?(winmm|version|dbghelp|wininet|winhttp|dxgi|d3d12)\.dll`?", re.I)
_STORE_ONLY = re.compile(r"\b(?:xbox|game ?pass|ms store|microsoft store)\b", re.I)
_LINUX = re.compile(r"\blinux\b", re.I)
_HEDGED = re.compile(r"\b(?:might|may)\b", re.I)
_REFRAMEWORK = re.compile(r"\bREFramework\b", re.I)
_NVNGX = re.compile(r"(?:copy|requires a copy of|place|add)[^.]{0,40}nvngx_dlss\.dll", re.I)
_ANTI_CHEAT = re.compile(r"\b(?:EAC|EasyAntiCheat|anti-?cheat)\b[^.]{0,30}\bdisabled\b|\bdisable\b[^.]{0,30}\b(?:EAC|anti-?cheat)\b", re.I)


def clean(name: str) -> str:
    name = re.sub("[™®©]", "", name)
    text = "".join(c if c.isalnum() else " " for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def variants(name: str) -> list[str]:
    """The name as written, then without a trailing "(2024)" or "Demo"."""
    plain = re.sub(r"\s*\((?:19|20)\d\d\)\s*$", "", name)
    return list(dict.fromkeys(clean(n) for n in (name, plain, re.sub(r"\s+Demo$", "", plain, flags=re.I))))


def facts(status: str, patcher: str, notes: str) -> dict:
    result: dict = {}
    if "❌" in status:
        result["status"] = "broken"
    if _DX12.search(notes):
        result["args"] = ["-dx12"]
    proxy = _PROXY.search(notes)
    store_only = _STORE_ONLY.search(notes) and not _LINUX.search(notes)
    if proxy and proxy.group(1).lower() != "dxgi" and not store_only and not _HEDGED.search(notes):
        result["proxy"] = f"{proxy.group(1).lower()}.dll"
    needs = [need for need, pattern in (("reframework", _REFRAMEWORK), ("nvngx_dlss", _NVNGX), ("anti_cheat_off", _ANTI_CHEAT))
             if pattern.search(notes)]
    if needs:
        result["needs"] = needs
    if "✨" in patcher:
        result["optipatcher"] = True
    return result


def parse(text: str) -> dict[str, dict]:
    """Clean game name -> facts, for rows that carry any."""
    rows: dict[str, dict] = {}
    for line in text.splitlines():
        match = _ROW.match(line)
        if not match:
            continue
        name = match["name"]
        link = _LINK.search(name)
        if link:
            name = link.group(1)
        key = clean(name)
        if not key or key in ("game", "game name") or set(name) <= set("-: "):
            continue
        found = facts(match["status"], match["patcher"], match["notes"])
        if found:
            rows.setdefault(key, found)
    return rows


class WikiCache:
    def __init__(self, folder: Path):
        self.path = folder / "optiscaler-wiki.json"
        self._rows: dict[str, dict] | None = None

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def rows(self) -> dict[str, dict]:
        if self._rows is None:
            self._rows = self._read().get("rows") or {}
        return self._rows

    def lookup(self, *names: str | None) -> dict | None:
        rows = self.rows()
        for name in names:
            for key in variants(name or ""):
                if key and key in rows:
                    return rows[key]
        return None

    def refresh(self, fetch=urllib.request.urlopen, now=time.time) -> dict:
        """Fetch only when the copy is old, and then only if the wiki changed; failures keep the copy."""
        cached = self._read()
        if cached.get("rows") is not None and cached.get("fetched_at", 0) > now() - MAX_AGE_S:
            return {"updated": False, "fresh": True}
        headers = {"User-Agent": "panel-de-control-upscalers"}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        try:
            with fetch(urllib.request.Request(URL, headers=headers), timeout=TIMEOUT_S, context=ssl_context()) as response:
                body = response.read(MAX_BYTES + 1)
                etag = response.headers.get("ETag")
        except urllib.error.HTTPError as error:
            if error.code == 304:
                self._write({**cached, "fetched_at": now()})
                return {"updated": False, "fresh": True}
            return {"updated": False, "fresh": False}
        except (OSError, ValueError):
            return {"updated": False, "fresh": False}
        if len(body) > MAX_BYTES:
            return {"updated": False, "fresh": False}
        rows = parse(body.decode("utf-8", "replace"))
        changed = rows != cached.get("rows")
        self._write({"rows": rows, "etag": etag, "fetched_at": now()})
        self._rows = rows
        return {"updated": changed, "fresh": True}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(self.path)
