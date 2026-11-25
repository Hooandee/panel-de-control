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


def own_with_parents(home: Path, path: Path) -> None:
    """A file Panel wrote under the user's home, and every folder it had to create on the way, become the user's."""
    if os.geteuid() != 0:
        return
    try:
        stat = home.stat()
        root = os.path.realpath(home)
    except OSError:
        return
    for item in [path, *path.parents]:
        if os.path.realpath(item) == root or os.path.commonpath([root, os.path.realpath(item)]) != root:
            break
        if item.is_symlink():
            continue
        try:
            os.chown(item, stat.st_uid, stat.st_gid, follow_symlinks=False)
        except OSError:
            pass


def own_like_ancestor(path: Path) -> None:
    """A file root wrote among the user's files takes the owner of its nearest folder that isn't root's.

    Nothing changes if any step of the way is a symlink, so a link can never point root's chown elsewhere.
    """
    if os.geteuid() != 0:
        return
    chain = [path]
    for parent in path.parents:
        try:
            if any(os.path.islink(p) for p in (path, *chain, parent)):
                return
            stat = os.lstat(parent)
        except OSError:
            return
        if stat.st_uid != 0:
            owner_root = os.path.realpath(parent)
            for item in chain:
                if os.path.commonpath([owner_root, os.path.realpath(item)]) != owner_root:
                    return
            for item in chain:
                try:
                    os.chown(item, stat.st_uid, stat.st_gid, follow_symlinks=False)
                except OSError:
                    pass
            return
        chain.append(parent)
