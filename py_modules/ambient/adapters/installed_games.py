from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import TypedDict

from pdc_platform.steam_paths import steam_roots

_TOKEN = re.compile(r'\s+|//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])')
_APPID = re.compile(r"[1-9][0-9]{0,9}")
_MAX_VDF_BYTES = 8 * 1024 * 1024


class InstalledGamesSnapshot(TypedDict):
    installed: list[str]
    libraries: dict[str, list[int]]
    complete: bool


def _document(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("not_regular")
        raw = handle.read(_MAX_VDF_BYTES + 1)
    if len(raw) > _MAX_VDF_BYTES:
        raise ValueError("too_large")
    text = raw.decode("utf-8-sig")
    tokens = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            raise ValueError("invalid_token")
        position = match.end()
        if match.group(1) is not None:
            value = re.sub(r'\\(["\\])', r'\1', match.group(1))
            tokens.append(("string", value))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
    cursor = 0

    def object_value(nested: bool = False, depth: int = 0) -> dict:
        nonlocal cursor
        if depth > 16:
            raise ValueError("too_deep")
        result = {}
        while cursor < len(tokens):
            kind, key = tokens[cursor]
            cursor += 1
            if kind == "}" and nested:
                return result
            if kind != "string" or key.lower() in result or cursor == len(tokens):
                raise ValueError("invalid_key")
            kind, value = tokens[cursor]
            cursor += 1
            if kind == "{":
                value = object_value(True, depth + 1)
            elif kind != "string":
                raise ValueError("invalid_value")
            result[key.lower()] = value
        if nested:
            raise ValueError("unclosed_object")
        return result

    return object_value()


def _identity(root: Path) -> list[int]:
    info = root.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("not_directory")
    return [info.st_dev, info.st_ino]


def _directory_state(directory: Path) -> tuple[int, int, int, int]:
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("not_directory")
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


def snapshot(home: str, previous_libraries: dict[str, list[int]] | None = None) -> InstalledGamesSnapshot:
    libraries = {path: list(identity) for path, identity in (previous_libraries or {}).items()}
    roots = steam_roots(home)
    complete = bool(roots)
    candidates = set(roots) | {Path(path) for path in libraries}
    for root in roots:
        try:
            index = _document(root / "steamapps/libraryfolders.vdf").get("libraryfolders")
            if not isinstance(index, dict):
                raise ValueError("missing_index")
            for key, entry in index.items():
                if not key.isdecimal():
                    continue
                path = entry.get("path") if isinstance(entry, dict) else None
                if not isinstance(path, str) or not os.path.isabs(path) or "\0" in path:
                    raise ValueError("invalid_library")
                candidates.add(Path(path).resolve())
        except (OSError, ValueError, RuntimeError):
            complete = False
    directories = {}
    for root in candidates:
        directory = root / "steamapps"
        try:
            directories[directory] = _directory_state(directory)
        except (OSError, ValueError):
            complete = False
    installed: set[str] = set()
    for root in sorted(candidates):
        key = str(root)
        try:
            identity = _identity(root)
            if key in libraries and libraries[key] != identity:
                complete = False
            else:
                libraries[key] = identity
            with os.scandir(root / "steamapps") as entries:
                paths = sorted(Path(entry.path) for entry in entries if entry.name.startswith("appmanifest_") and entry.name.endswith(".acf"))
            for path in paths:
                try:
                    state = _document(path).get("appstate")
                    appid = state.get("appid") if isinstance(state, dict) else None
                    if not isinstance(appid, str) or not _APPID.fullmatch(appid) or int(appid) >= 2**31 or path.name != f"appmanifest_{appid}.acf":
                        raise ValueError("invalid_appid")
                    installed.add(appid)
                except (OSError, ValueError):
                    complete = False
            if _identity(root) != identity:
                complete = False
        except (OSError, ValueError):
            complete = False
    for directory, before in directories.items():
        try:
            if _directory_state(directory) != before:
                complete = False
        except (OSError, ValueError):
            complete = False
    return {"installed": sorted(installed, key=int), "libraries": libraries, "complete": complete}
