import os
import stat
from pathlib import Path

from . import filesystem


MAX_SCREENSHOTS = 500


def _steam_roots(home):
    roots = []
    for relative in (".local/share/Steam", ".steam/steam", ".steam/root"):
        try:
            root = (Path(home) / relative).resolve(strict=True)
            if root not in roots:
                roots.append(root)
        except (OSError, RuntimeError):
            continue
    return roots


def _screenshot_root(path, roots):
    for root in roots:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        parts = relative.parts
        if (
            len(parts) == 7
            and parts[0] == "userdata"
            and parts[1].isdecimal()
            and parts[2:4] == ("760", "remote")
            and parts[4].isdecimal()
            and parts[5] == "screenshots"
            and parts[6] not in ("", ".", "..")
        ):
            return root
    return None


def measure_screenshot_paths(home, paths):
    if not isinstance(paths, list):
        return {}
    roots = _steam_roots(home)
    result = {}
    for raw in paths[:MAX_SCREENSHOTS]:
        if not isinstance(raw, str) or not os.path.isabs(raw) or os.path.normpath(raw) != raw or "\0" in raw:
            if isinstance(raw, str):
                result[raw] = None
            continue
        path = Path(raw)
        if _screenshot_root(path, roots) is None:
            result[raw] = None
            continue
        try:
            with filesystem.open_directory(str(path.parent)) as (parent_fd, _):
                value = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                result[raw] = value.st_size if stat.S_ISREG(value.st_mode) else None
        except (OSError, filesystem.UnsafePath):
            result[raw] = None
    return result
