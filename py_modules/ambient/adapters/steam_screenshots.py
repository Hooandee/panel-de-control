from __future__ import annotations

import glob
import os

from pdc_platform.steam_paths import steam_roots


def screenshot_folders(home: str) -> list[str]:
    folders: list[str] = []
    for root in steam_roots(home):
        pattern = os.path.join(str(root), "userdata", "[0-9]*", "760", "remote", "[0-9]*", "screenshots")
        for path in sorted(glob.glob(pattern)):
            real = os.path.realpath(path)
            if os.path.isdir(real) and real not in folders:
                folders.append(real)
    return folders
