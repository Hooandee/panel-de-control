from __future__ import annotations

from pathlib import Path

_STEAM_ROOT_CANDIDATES = (".local/share/Steam", ".steam/steam", ".steam/root")


def steam_roots(home: str) -> list[Path]:
    roots: list[Path] = []
    for relative in _STEAM_ROOT_CANDIDATES:
        try:
            root = (Path(home) / relative).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if root not in roots:
            roots.append(root)
    return roots
