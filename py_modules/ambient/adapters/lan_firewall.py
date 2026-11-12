from __future__ import annotations

import shutil
import subprocess
from typing import Callable, Optional, Sequence

from pdc_platform.host_env import clean_env

_TIMEOUT_SEC = 4

Runner = Callable[[Sequence[str]], tuple[int, str]]


def _run(command: Sequence[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(list(command), capture_output=True, text=True, timeout=_TIMEOUT_SEC, env={**clean_env(), "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return -1, ""
    return done.returncode, done.stdout.strip()


def _interface_of(address: str, run: Runner) -> Optional[str]:
    code, out = run(["ip", "-o", "-4", "addr", "show"])
    if code != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[3].split("/", 1)[0] == address:
            return parts[1]
    return None


def open_port(port: int, address: str, seconds: int, run: Runner = _run, which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """Lets the phone reach the share page through firewalld (Bazzite and other Fedora images enable it).

    Runtime rule only, never --permanent, and firewalld drops it by itself after `seconds`. SteamOS
    ships no firewall, so there this does nothing. Returns what happened, for the report.
    """
    tool = which("firewall-cmd")
    if not tool:
        return "none"
    code, state = run([tool, "--state"])
    if code != 0 or state != "running":
        return "inactive"
    interface = _interface_of(address, run)
    zone = ""
    if interface:
        code, zone = run([tool, f"--get-zone-of-interface={interface}"])
        zone = zone if code == 0 else ""
    if not zone:
        code, zone = run([tool, "--get-default-zone"])
        if code != 0 or not zone:
            return "no_zone"
    code, _ = run([tool, f"--zone={zone}", f"--add-port={port}/tcp", f"--timeout={max(1, int(seconds))}s"])
    return f"opened:{zone}" if code == 0 else f"failed:{zone}:{code}"
