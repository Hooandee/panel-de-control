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
FIREFOX = "/usr/bin/firefox"

Run = Callable[[list[str]], str]


@dataclass(frozen=True)
class SecondaryDisplay:
    mechanism: str
    connector: str
    touchscreen: str
    session: UserSession


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
    if not exists(FIREFOX):
        return Detection(None, "no_browser")
    if not exists(ARMADA_LEASE_SOCKET):
        return Detection(None, "not_in_game_mode")
    try:
        session = session_for_uid(owner_uid(ARMADA_LEASE_SOCKET))
    except OSError:
        session = None
    if session is None:
        return Detection(None, "no_session")
    return Detection(SecondaryDisplay("armada-lease", connector, touchscreen, session), "ok")
