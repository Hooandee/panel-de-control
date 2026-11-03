"""Give what Panel created inside a user's folder to that folder's owner, without ever leaving it.

Decky runs Panel as root inside folders the user can write to, so a symlink planted there must never
make root chown something outside: walks never follow links and every path is checked to stay inside.
"""

import os
from pathlib import Path


def own_like(folder: Path, paths: list[Path]) -> None:
    if os.geteuid() != 0:
        return
    try:
        stat = folder.stat()
        root = os.path.realpath(folder)
    except OSError:
        return
    for path in paths:
        if path.is_symlink():
            continue
        items = [path]
        if path.is_dir():
            for current, dirs, files in os.walk(path, followlinks=False):
                items += [Path(current) / name for name in (*dirs, *files)]
        for item in items:
            if item.is_symlink() or os.path.commonpath([root, os.path.realpath(item)]) != root:
                continue
            try:
                os.chown(item, stat.st_uid, stat.st_gid, follow_symlinks=False)
            except OSError:
                pass
