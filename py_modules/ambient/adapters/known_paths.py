from __future__ import annotations

import os
import re

_XDG_KEYS = {"images": "XDG_PICTURES_DIR", "videos": "XDG_VIDEOS_DIR", "music": "XDG_MUSIC_DIR"}
_FALLBACK = {"images": "Pictures", "videos": "Videos", "music": "Music"}
_LINE = re.compile(r'^\s*(XDG_[A-Z]+_DIR)\s*=\s*"(.*)"\s*$')


def _xdg_dirs(home: str) -> dict[str, str]:
    path = os.path.join(home, ".config", "user-dirs.dirs")
    found: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                match = _LINE.match(line)
                if match:
                    found[match.group(1)] = match.group(2).replace("$HOME", home)
    except OSError:
        pass
    return found


def known_folders(home: str) -> dict[str, list[str]]:
    """The user's picture, video and music folders that actually exist (XDG first)."""
    xdg = _xdg_dirs(home)
    result: dict[str, list[str]] = {}
    for kind, key in _XDG_KEYS.items():
        candidates = [xdg[key]] if key in xdg else []
        candidates.append(os.path.join(home, _FALLBACK[kind]))
        existing = [c for c in dict.fromkeys(candidates) if os.path.isdir(c) and os.path.realpath(c) != os.path.realpath(home)]
        result[kind] = existing[:1]
    return result
