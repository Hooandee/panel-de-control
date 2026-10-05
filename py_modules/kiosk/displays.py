"""Which secondary display this machine has and how to put a page on it."""

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable

from controllers.detect import clean_env
from user_session import UserSession, session_for_uid

ARMADA_RUN_BOTTOM = "/usr/bin/armada-run-bottom"
ARMADA_DEVICE_ENV = "/usr/libexec/armada/device-env"
ARMADA_LEASE_SOCKET = "/tmp/gamescope-lease.sock"
SYSTEM_PYTHON = "/usr/bin/python3"

Run = Callable[[list[str]], str]

# FB_BLANK_POWERDOWN / FB_BLANK_UNBLANK for /sys/class/backlight/*/bl_power.
BACKLIGHT_OFF = "4"
BACKLIGHT_ON = "0"


MIN_BACKLIGHT_FRACTION = 0.05


def _backlight_dir(backlight: str, sys_root: str) -> str | None:
    if not backlight or "/" in backlight or backlight.startswith("."):
        return None
    return os.path.join(sys_root, backlight)


def set_backlight_power(backlight: str, on: bool, sys_root: str = "/sys/class/backlight") -> bool:
    folder = _backlight_dir(backlight, sys_root)
    if folder is None:
        return False
    try:
        with open(os.path.join(folder, "bl_power"), "w") as handle:
            handle.write(BACKLIGHT_ON if on else BACKLIGHT_OFF)
        return True
    except OSError:
        return False


def _read_int(path: str) -> int | None:
    try:
        with open(path) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def backlight_level(backlight: str, sys_root: str = "/sys/class/backlight") -> float | None:
    folder = _backlight_dir(backlight, sys_root)
    if folder is None:
        return None
    value = _read_int(os.path.join(folder, "brightness"))
    maximum = _read_int(os.path.join(folder, "max_brightness"))
    if value is None or not maximum:
        return None
    return round(value / maximum, 3)


def set_backlight_level(backlight: str, fraction: float, sys_root: str = "/sys/class/backlight") -> float | None:
    folder = _backlight_dir(backlight, sys_root)
    maximum = _read_int(os.path.join(folder, "max_brightness")) if folder else None
    if folder is None or not maximum:
        return None
    wanted = min(1.0, max(MIN_BACKLIGHT_FRACTION, float(fraction)))
    try:
        with open(os.path.join(folder, "brightness"), "w") as handle:
            handle.write(str(max(1, round(wanted * maximum))))
    except OSError:
        return None
    return backlight_level(backlight, sys_root)


@dataclass(frozen=True)
class SecondaryDisplay:
    mechanism: str
    connector: str
    touchscreen: str
    session: UserSession
    backlight: str = ""


@dataclass(frozen=True)
class Detection:
    display: SecondaryDisplay | None
    reason: str


def _run(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, env=clean_env(), capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_device_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, raw = line.partition("=")
        if not sep or not key.isidentifier():
            continue
        try:
            parts = shlex.split(raw)
        except ValueError:
            continue
        values[key] = parts[0] if parts else ""
    return values


def detect(
    exists: Callable[[str], bool] = os.path.exists,
    owner_uid: Callable[[str], int] = lambda path: os.stat(path).st_uid,
    run: Run = _run,
) -> Detection:
    if not exists(ARMADA_RUN_BOTTOM):
        return Detection(None, "no_mechanism")
    env = parse_device_env(run([ARMADA_DEVICE_ENV]))
    connector = env.get("ARMADA_SECONDARY_CONNECTOR", "")
    touchscreen = env.get("ARMADA_SECONDARY_TOUCHSCREEN", "")
    if not connector or not touchscreen:
        return Detection(None, "no_secondary_display")
    if not exists(SYSTEM_PYTHON):
        return Detection(None, "no_runtime")
    if not exists(ARMADA_LEASE_SOCKET):
        return Detection(None, "not_in_game_mode")
    try:
        session = session_for_uid(owner_uid(ARMADA_LEASE_SOCKET))
    except OSError:
        session = None
    if session is None:
        return Detection(None, "no_session")
    backlight = env.get("ARMADA_SECONDARY_BACKLIGHT", "")
    return Detection(SecondaryDisplay("armada-lease", connector, touchscreen, session, backlight), "ok")
