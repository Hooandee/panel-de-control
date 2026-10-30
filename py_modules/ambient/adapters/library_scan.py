from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..core.media_types import media_kind

DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FILES = 2000


@dataclass
class ScanResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    missing: bool = False


def media_id(path: str) -> str:
    return "local:" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:20]


def scan_folder(
    root: str,
    kinds: Iterable[str],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
) -> ScanResult:
    wanted = set(kinds)
    result = ScanResult()
    if not os.path.isdir(root):
        result.missing = True
        return result
    stack: list[tuple[str, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name, reverse=True)
        except OSError:
            continue
        files, subdirs = [], []
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    subdirs.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
            except OSError:
                continue
        for entry in reversed(files):
            kind = media_kind(entry.name)
            if kind not in wanted:
                continue
            if len(result.items) >= max_files:
                result.truncated = True
                return result
            stat = entry.stat(follow_symlinks=False)
            result.items.append({
                "id": media_id(entry.path),
                "path": entry.path,
                "name": entry.name,
                "kind": kind,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            })
        if depth < max_depth:
            stack.extend((d.path, depth + 1) for d in subdirs)
    return result
