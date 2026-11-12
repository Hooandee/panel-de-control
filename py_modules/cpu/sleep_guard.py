"""Brings every CPU core back online right before the system sleeps.

Sleeping with cores switched off can freeze the machine on resume. A runtime systemd
unit ordered before sleep.target runs even when the plugin is busy or stuck, and /run
is gone after a reboot.
"""
from __future__ import annotations

import os
import subprocess

from pdc_platform.host_env import clean_env, resolve_bin

UNIT_NAME = "panel-de-control-sleep-cores.service"
_TIMEOUT_S = 10

# systemd expands $VAR in ExecStart: $$ passes a literal dollar to the shell.
UNIT_TEXT = """[Unit]
Description=Panel de Control: CPU cores online before sleep
Before=sleep.target

[Service]
Type=oneshot
TimeoutStartSec=10
ExecStart=/bin/sh -c 'for f in /sys/devices/system/cpu/cpu[0-9]*/online; do [ "$$(cat "$$f" 2>/dev/null)" = 0 ] && echo 1 > "$$f"; done; exit 0'
"""


def _run_systemctl(*args: str) -> bool:
    try:
        result = subprocess.run(
            [resolve_bin("systemctl"), *args],
            check=False, capture_output=True, text=True,
            timeout=_TIMEOUT_S, env=clean_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


class SleepCoreGuard:
    def __init__(self, root: str = "/", systemctl=_run_systemctl):
        self._dir = os.path.join(root, "run/systemd/system")
        self._unit = os.path.join(self._dir, UNIT_NAME)
        self._link = os.path.join(self._dir, "sleep.target.wants", UNIT_NAME)
        self._systemctl = systemctl
        self.last_error: str | None = None

    @property
    def installed(self) -> bool:
        try:
            with open(self._unit) as f:
                current = f.read()
        except OSError:
            return False
        return current == UNIT_TEXT and os.path.islink(self._link)

    def ensure(self) -> bool:
        """Idempotent: installs the unit and reloads systemd only when missing."""
        if self.installed:
            return True
        try:
            os.makedirs(os.path.dirname(self._link), exist_ok=True)
            tmp = f"{self._unit}.tmp"
            with open(tmp, "w") as f:
                f.write(UNIT_TEXT)
            os.replace(tmp, self._unit)
            if os.path.lexists(self._link):
                os.unlink(self._link)
            os.symlink(os.path.join("..", UNIT_NAME), self._link)
        except OSError as error:
            self.last_error = f"write:{type(error).__name__}"
            return False
        if not self._systemctl("daemon-reload"):
            self.last_error = "daemon_reload_failed"
            return False
        self.last_error = None
        return True

    def remove(self, reload: bool = True) -> bool:
        """reload=False (unload) skips daemon-reload to keep the stop fast; until the
        next reload systemd may still run the unit, which then finds nothing to do."""
        present = False
        for path in (self._link, self._unit):
            try:
                os.unlink(path)
                present = True
            except FileNotFoundError:
                pass
            except OSError as error:
                self.last_error = f"remove:{type(error).__name__}"
                return False
        if present and reload and not self._systemctl("daemon-reload"):
            self.last_error = "daemon_reload_failed"
            return False
        return True

    def diagnostics(self) -> dict:
        return {"installed": self.installed, "last_error": self.last_error}
