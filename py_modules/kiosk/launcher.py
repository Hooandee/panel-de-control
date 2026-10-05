"""Start, watch and stop the bottom screen as a transient user unit in the game session."""

import os
import subprocess
import time
from typing import Callable

from kiosk.displays import SYSTEM_PYTHON, SecondaryDisplay
from user_session import spawn_args

UNIT = "pdc-kiosk"
URL_ENV = "PDC_KIOSK_URL"
_HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.join(_HERE, "native", "app.py")
NATIVE_ASSETS = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "dist", "kiosk")

Runner = Callable[[list[str], dict, dict], tuple[int, str]]


def _default_runner(cmd: list[str], env: dict, identity: dict) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10, check=False, **identity)
        return done.returncode, (done.stdout or done.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def launch_argv(native: str = NATIVE, assets: str = NATIVE_ASSETS) -> list[str]:
    return [SYSTEM_PYTHON, native, assets]


NICE = 10
CPU_WEIGHT = 20


class KioskLauncher:
    def __init__(self, display: SecondaryDisplay, runner: Runner = _default_runner):
        self.display = display
        self.runner = runner
        self._started_at: int | None = None

    def _systemd(self, argv: list[str]) -> tuple[int, str]:
        cmd, env, identity = spawn_args(self.display.session, argv)
        return self.runner(cmd, env, identity)

    def start(self, url: str) -> tuple[bool, str]:
        self._started_at = int(time.time())
        self._systemd(["systemctl", "--user", "reset-failed", UNIT])
        code, out = self._systemd([
            "systemd-run", "--user", f"--unit={UNIT}", "--collect", "--quiet",
            # The bottom screen must never take CPU time from the game on the top one.
            f"--nice={NICE}", f"--property=CPUWeight={CPU_WEIGHT}",
            # In the environment, not argv: any local user can read a command line.
            f"--setenv={URL_ENV}={url}",
            *launch_argv(),
        ])
        return code == 0, out

    def last_words(self) -> str:
        if self._started_at is None:
            return ""
        # The unit's own output only, not the service manager's lines about it.
        code, out = self._systemd(["journalctl", "--user", f"_SYSTEMD_USER_UNIT={UNIT}.service",
                                   f"--since=@{self._started_at}", "--lines=2", "--output=cat", "--no-pager"])
        return out[-300:] if code == 0 else ""

    def is_active(self) -> bool:
        code, out = self._systemd(["systemctl", "--user", "is-active", UNIT])
        return code == 0 and out == "active"

    def stop(self) -> tuple[bool, str]:
        # --no-block: Decky SIGKILLs a plugin that takes 5 s to unload, and a killed plugin
        # can leave the loader spinning. The transient unit is --collect, so nothing lingers.
        code, out = self._systemd(["systemctl", "--user", "stop", "--no-block", UNIT])
        return code == 0, out
