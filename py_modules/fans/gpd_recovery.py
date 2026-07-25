"""Load ``gpd_fan`` only for the exact GPD Win Mini 2025 DMI."""

import glob
import os
import subprocess
import time

from device_quirks import is_gpd_win_mini_2025


_HWMON = "sys/class/hwmon"
_CHIP_NAME = "gpdfan"
_REQUIRED_NODES = ("fan1_input", "pwm1", "pwm1_enable")


def _read(path: str) -> str:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def gpdfan_abi_complete(root: str = "/") -> bool:
    pattern = os.path.join(root, _HWMON, "hwmon*")
    for directory in sorted(glob.glob(pattern)):
        if _read(os.path.join(directory, "name")) != _CHIP_NAME:
            continue
        if all(os.path.exists(os.path.join(directory, node)) for node in _REQUIRED_NODES):
            return True
    return False


def _default_run(command: list[str]):
    from controllers.detect import clean_env, resolve_bin

    argv = [resolve_bin(command[0]), *command[1:]]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
        env=clean_env(),
    )


def _wait_for_abi(check, *, timeout: float = 1.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(interval)
    return check()


def ensure_gpd_fan(
    device,
    *,
    root: str = "/",
    run=_default_run,
    wait_for_abi=_wait_for_abi,
) -> dict:
    """Try once and return bounded diagnostics without process output."""
    outcome = {
        "eligible": False,
        "abi_before": False,
        "attempted": False,
        "exit": None,
        "error": None,
        "abi_after": False,
    }
    outcome["eligible"] = is_gpd_win_mini_2025(device, root)
    if not outcome["eligible"]:
        return outcome

    outcome["abi_before"] = gpdfan_abi_complete(root)
    if outcome["abi_before"]:
        outcome["abi_after"] = True
        return outcome

    outcome["attempted"] = True
    try:
        result = run(["modprobe", "gpd_fan"])
        outcome["exit"] = int(getattr(result, "returncode", 0) or 0)
        if outcome["exit"] == 0:
            wait_for_abi(lambda: gpdfan_abi_complete(root))
    except Exception as exc:  # noqa: BLE001 — recovery must never break plugin load
        outcome["error"] = type(exc).__name__

    outcome["abi_after"] = gpdfan_abi_complete(root)
    return outcome
