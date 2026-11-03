"""The OptiScaler wiki read in full: every row of the compatibility tables and each game's own page.

Only facts are kept, never the note text: the community verdict, the upscaler inputs, OptiPatcher
support, -dx12, the proxy name, what else the game needs (REFramework, nvngx_dlss.dll, anti-cheat
off, a third-party mod), whether someone tested it on Linux and the OptiScaler.ini settings the page
lists. The same parser builds the bundled recipes_wiki.json and reads the live copy on the device.
"""

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler/Compatibility-List.md"
PAGE_URL = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler/{}.asciidoc"
MAX_AGE_S = 6 * 3600
PAGE_MAX_AGE_S = 24 * 3600
TIMEOUT_S = 8
MAX_BYTES = 4 * 1024 * 1024
PAGE_MAX_BYTES = 256 * 1024
# Bumped whenever parse() keeps new facts, so a copy saved by an older Panel is fetched again.
FORMAT = 2

_ROW = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_DX12 = re.compile(r"(?<![\w-])-dx12\b", re.I)
_PROXY = re.compile(r"\b(?:as|rename(?:d)? (?:it )?to|use)\s+`?(winmm|version|dbghelp|wininet|winhttp|dxgi|d3d12)\.dll`?", re.I)
_STORE_ONLY = re.compile(r"\b(?:xbox|game ?pass|ms store|microsoft store)\b", re.I)
_LINUX = re.compile(r"\b(?:linux|steamos|steam ?deck|proton|wine|bazzite|cachyos)\b", re.I)
_HEDGED = re.compile(r"\b(?:might|may)\b", re.I)
_REFRAMEWORK = re.compile(r"\bREFramework\b", re.I)
_NVNGX = re.compile(r"(?:copy|requires a copy of|place|add)[^.]{0,40}nvngx_dlss\.dll", re.I)
_ANTI_CHEAT = re.compile(r"\b(?:EAC|EasyAntiCheat|anti-?cheat)\b[^.]{0,30}\bdisabled\b|\bdisable\b[^.]{0,30}\b(?:EAC|anti-?cheat)\b", re.I)
_MOD = re.compile(r"\brequires?\b[^.|]{0,60}\bmod\b|\bLuma\b", re.I)
_INPUTS = ("DLSS", "FSR2", "FSR3", "FSR3.1", "FSR4", "XeSS", "DLSSG", "FSR FG", "XeFG")
_PAGE_FIELD = re.compile(r"^\|\*\*(?P<name>[^*]+)\*\*\s*$", re.M)
_SETTING = re.compile(r"`\s*(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*=\s*(?P<value>[^`\s]+)\s*`")
# Settings that only hold for another API, vendor or feature than the one Panel installs for.
_CONDITIONAL = re.compile(r"\b(?:if|when|for|only|optional(?:ly)?|try|vulkan|nvidia|rtx|intel arc|dx11|optifg|fg)\b", re.I)
_AMD = re.compile(r"\b(?:amd|radeon|rdna)\b", re.I)
_AUTOAPPLIED = re.compile(r"auto-?applied", re.I)
_FILENAME = re.compile(r"`?([A-Za-z0-9_]+\.(?:dll|asi))`?", re.I)
_SECTIONS = {"upscaler mods support": "mod", "luma unreal engine": "luma"}


def clean(name: str) -> str:
    name = re.sub("[™®©]", "", name)
    text = "".join(c if c.isalnum() else " " for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def variants(name: str) -> list[str]:
    """The name as written, then without a trailing "(2024)" or "Demo"."""
    plain = re.sub(r"\s*\((?:19|20)\d\d\)\s*$", "", name)
    return list(dict.fromkeys(clean(n) for n in (name, plain, re.sub(r"\s+Demo$", "", plain, flags=re.I))))


def _status(cell: str) -> str:
    if "❌" in cell:
        return "broken"
    if "➖" in cell:
        return "partial"
    return "works"


def _inputs(cell: str) -> list[str]:
    found = []
    for part in re.split(r"[,/]|<br>", cell):
        token = part.strip().replace(" ", "").lower()
        for known in _INPUTS:
            if token == known.replace(" ", "").lower() and known not in found:
                found.append(known)
    return found


def facts(status: str, patcher: str, notes: str, table: str = "main") -> dict:
    result: dict = {"status": _status(status)}
    if _DX12.search(notes):
        result["args"] = ["-dx12"]
    proxy = _PROXY.search(notes)
    store_only = _STORE_ONLY.search(notes) and not _LINUX.search(notes)
    if proxy and proxy.group(1).lower() != "dxgi" and not store_only and not _HEDGED.search(notes):
        result["proxy"] = f"{proxy.group(1).lower()}.dll"
    needs = [need for need, pattern in (("reframework", _REFRAMEWORK), ("nvngx_dlss", _NVNGX), ("anti_cheat_off", _ANTI_CHEAT))
             if pattern.search(notes)]
    if table == "luma" or (table in ("main", "mod") and re.search(r"\bLuma\b", notes, re.I)):
        needs.append("luma")
    elif table == "mod" or (_MOD.search(notes) and "reframework" not in needs):
        if "reframework" not in needs:
            needs.append("mod")
    if needs:
        result["needs"] = needs
    if "✨" in patcher:
        result["optipatcher"] = True
    return result


def parse(text: str) -> dict[str, dict]:
    """Clean game name -> facts, for every game the wiki lists."""
    rows: dict[str, dict] = {}
    table = "main"
    for line in text.splitlines():
        if line.startswith("## "):
            table = _SECTIONS.get(line[3:].strip().lower(), "main")
            continue
        match = _ROW.match(line)
        if not match:
            continue
        cells = [c.strip() for c in match["cells"].split("|")]
        if len(cells) < 4:
            continue
        name = cells[0]
        link = _LINK.search(name)
        page = None
        if link:
            name, page = link.group(1), link.group(2)
        key = clean(name)
        if not key or key in ("game", "game name") or set(name) <= set("-: "):
            continue
        if table == "main":
            status, inputs, patcher, notes = cells[1], cells[2], cells[3], cells[4] if len(cells) > 4 else ""
        else:
            status, inputs, patcher, notes = cells[1], cells[2], "", cells[3]
        if not re.search("[✅❌➖✔]", status) or "/" in status:
            continue
        found = {"name": name.strip()[:80], **facts(status, patcher, notes, table)}
        listed = _inputs(inputs)
        if listed:
            found["inputs"] = listed
        if page and not page.startswith("http") and "#" not in page:
            found["page"] = urllib.parse.unquote(page)[:120]
        rows.setdefault(key, found)
    return rows


def _fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    marks = list(_PAGE_FIELD.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        fields[mark["name"].strip().lower()] = text[mark.end():end].replace("|===", "").strip()
    return fields


def parse_page(text: str) -> dict:
    """A game's compatibility entry: proxy name, Linux testing and the OptiScaler.ini settings it lists."""
    fields = _fields(text)
    result: dict = {}
    names = [n.lower() for n in _FILENAME.findall(fields.get("filename", ""))]
    if names and names[0] != "dxgi.dll" and names[0].endswith(".dll"):
        result["proxy"] = names[0]
    if _LINUX.search(fields.get("os", "")):
        result["linux"] = True
    settings: dict[str, str] = {}
    suggestions: dict[str, str] = {}
    for line in re.split(r"\n(?=\*[^*])|\n\n", fields.get("settings", "")):
        if _AUTOAPPLIED.search(line):
            continue
        pairs = _SETTING.findall(line)
        if not pairs:
            continue
        conditional = bool(_CONDITIONAL.search(_SETTING.sub("", line))) and not _AMD.search(line)
        for key, value in pairs:
            (suggestions if conditional else settings).setdefault(key, value.strip(",.;"))
    if settings:
        result["settings"] = settings
    if suggestions:
        result["suggestions"] = suggestions
    return result


def resolve_settings(ini_text: str, settings: dict[str, str]) -> dict[str, str]:
    """`Key=value` pairs from the wiki mapped to `Section.Key`, only when the installed OptiScaler.ini has exactly
    one such key and the value is one it accepts; anything else is left for the user to decide."""
    from . import ini

    where: dict[str, list[tuple[str, dict]]] = {}
    for section in ini.schema(ini_text):
        for entry in section["keys"]:
            where.setdefault(entry["key"].lower(), []).append((section["name"], entry))
    resolved = {}
    for key, value in settings.items():
        found = where.get(key.lower(), [])
        if len(found) != 1:
            continue
        section, entry = found[0]
        choices = entry.get("choices")
        if choices and value.lower() not in [c.lower() for c in choices]:
            continue
        if not choices and not re.fullmatch(r"-?\d+(?:\.\d+)?|0x[0-9a-fA-F]+|true|false|auto", value, re.I):
            continue
        resolved[f"{section}.{entry['key']}"] = value
    return resolved


class WikiCache:
    def __init__(self, folder: Path):
        self.path = folder / "optiscaler-wiki.json"
        self.pages_path = folder / "optiscaler-wiki-pages.json"
        self._rows: dict[str, dict] | None = None
        self._pages: dict[str, dict] | None = None

    def _read(self, path: Path | None = None) -> dict:
        try:
            data = json.loads((path or self.path).read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _current(self) -> dict:
        cached = self._read()
        return cached if cached.get("format") == FORMAT else {}

    def rows(self) -> dict[str, dict]:
        if self._rows is None:
            self._rows = self._current().get("rows") or {}
        return self._rows

    def pages(self) -> dict[str, dict]:
        if self._pages is None:
            self._pages = self._read(self.pages_path)
        return self._pages

    def page_facts(self, slug: str | None) -> dict | None:
        return (self.pages().get(slug or "") or {}).get("facts")

    def lookup(self, *names: str | None) -> dict | None:
        rows = self.rows()
        for name in names:
            for key in variants(name or ""):
                if key and key in rows:
                    return rows[key]
        return None

    def _fetch(self, url: str, etag: str | None, limit: int, fetch) -> tuple[str, bytes | None, str | None]:
        from http_util import ssl_context

        headers = {"User-Agent": "panel-de-control-upscalers"}
        if etag:
            headers["If-None-Match"] = etag
        try:
            with fetch(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_S, context=ssl_context()) as response:
                body = response.read(limit + 1)
                new_etag = response.headers.get("ETag")
        except urllib.error.HTTPError as error:
            return ("same", None, None) if error.code == 304 else ("failed", None, None)
        except (OSError, ValueError):
            return "failed", None, None
        if len(body) > limit:
            return "failed", None, None
        return "new", body, new_etag

    def refresh(self, fetch=urllib.request.urlopen, now=time.time) -> dict:
        """Fetch only when the copy is old, and then only if the wiki changed; failures keep the copy."""
        cached = self._current()
        if cached.get("rows") is not None and cached.get("fetched_at", 0) > now() - MAX_AGE_S:
            return {"updated": False, "fresh": True}
        outcome, body, etag = self._fetch(URL, cached.get("etag"), MAX_BYTES, fetch)
        if outcome == "same":
            self._write(self.path, {**cached, "fetched_at": now()})
            return {"updated": False, "fresh": True}
        if outcome == "failed" or body is None:
            return {"updated": False, "fresh": False}
        rows = parse(body.decode("utf-8", "replace"))
        changed = rows != cached.get("rows")
        self._write(self.path, {"format": FORMAT, "rows": rows, "etag": etag, "fetched_at": now()})
        self._rows = rows
        return {"updated": changed, "fresh": True}

    def refresh_page(self, slug: str | None, fetch=urllib.request.urlopen, now=time.time) -> dict:
        """One game's entry, fetched when its detail opens and kept for a day."""
        if not slug or "/" in slug or ".." in slug:
            return {"updated": False, "fresh": True}
        pages = dict(self.pages())
        cached = pages.get(slug) or {}
        if cached.get("fetched_at", 0) > now() - PAGE_MAX_AGE_S:
            return {"updated": False, "fresh": True}
        outcome, body, etag = self._fetch(PAGE_URL.format(urllib.parse.quote(slug)), cached.get("etag"), PAGE_MAX_BYTES, fetch)
        if outcome == "failed":
            return {"updated": False, "fresh": False}
        page = cached.get("facts") if outcome == "same" or body is None else parse_page(body.decode("utf-8", "replace"))
        pages[slug] = {"facts": page or {}, "etag": etag or cached.get("etag"), "fetched_at": now()}
        self._write(self.pages_path, pages)
        self._pages = pages
        return {"updated": (page or {}) != (cached.get("facts") or {}), "fresh": True}

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
