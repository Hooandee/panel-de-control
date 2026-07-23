"""Detect host tools that launch-option pills depend on. Never raises.

Drives honest pill availability (a pill whose tool is absent shows disabled) and
the locale caveat (forcing LANG is unreliable on stock SteamOS's stripped glibc).
"""

import os
import shutil

from osinfo import read_os_id


def _which(which, name: str) -> bool:
    try:
        return bool(which(name))
    except Exception:  # noqa: BLE001
        return False


def detect_tools(root: str = "/", home: str | None = None, which=shutil.which) -> dict:
    home = home or os.path.expanduser("~")
    # lsfg-vk: the Decky plugin drops a ~/lsfg wrapper; its config dir also marks it.
    try:
        lsfg = os.path.exists(os.path.join(home, "lsfg")) or os.path.isdir(
            os.path.join(home, ".config", "lsfg-vk")
        )
    except Exception:  # noqa: BLE001
        lsfg = False
    distro = read_os_id(root=root) or "other"
    return {
        "lsfg": lsfg,
        "mangohud": _which(which, "mangohud"),
        "gamemode": _which(which, "gamemoderun"),
        "gamescope": _which(which, "gamescope"),
        "distro": distro,
        # SteamOS ships a stripped glibc → LANG/LC_ALL forcing often silently fails.
        "locale_reliable": distro != "steamos",
    }
