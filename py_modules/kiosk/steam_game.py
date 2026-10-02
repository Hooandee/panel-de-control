"""Name and library artwork of a Steam game, read from the local Steam install."""

import os
from pathlib import Path

from steam_cleaner import vdf

ART_FILES = {
    "hero": ("library_hero.jpg", "image/jpeg"),
    "logo": ("logo.png", "image/png"),
    "header": ("header.jpg", "image/jpeg"),
}


def steam_roots(home: str) -> list[Path]:
    roots: list[Path] = []
    for candidate in (Path(home) / ".local/share/Steam", Path(home) / ".steam/steam"):
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _libraries(root: Path) -> list[Path]:
    libraries = [root]
    try:
        document = vdf.read_text(root / "steamapps/libraryfolders.vdf").get("libraryfolders")
    except (OSError, ValueError, UnicodeError):
        return libraries
    if not isinstance(document, dict):
        return libraries
    for key, value in document.items():
        raw = value.get("path") if isinstance(value, dict) else value
        if key.isdecimal() and isinstance(raw, str) and os.path.isabs(raw) and Path(raw) not in libraries:
            libraries.append(Path(raw))
    return libraries


def game_name(home: str, appid: str) -> str | None:
    if not appid.isdecimal():
        return None
    for root in steam_roots(home):
        for library in _libraries(root):
            try:
                state = vdf.read_text(library / f"steamapps/appmanifest_{appid}.acf").get("appstate")
            except (OSError, ValueError, UnicodeError):
                continue
            name = state.get("name") if isinstance(state, dict) else None
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def art_file(home: str, appid: str, kind: str) -> tuple[str, str] | None:
    """(path, content type) of a cached library image, or None. Steam keeps newer caches in hashed subfolders."""
    if not appid.isdecimal() or kind not in ART_FILES:
        return None
    name, content_type = ART_FILES[kind]
    for root in steam_roots(home):
        folder = root / "appcache/librarycache" / appid
        direct = folder / name
        if direct.is_file():
            return str(direct), content_type
        try:
            nested = sorted(folder.glob(f"*/{name}"))
        except OSError:
            nested = []
        if nested:
            return str(nested[0]), content_type
    return None
