"""Opt-in loading of a desktop motherboard's Super I/O fan driver.

Distros ship ``nct6775``/``it87``/… as modules but rarely autoload them, so a
desktop exposes no board fans until one is loaded. Each driver probes its own chip
ID and refuses to bind to foreign hardware, so trying the shipped candidates in
order is safe; parameters that bypass ACPI resource checks are never passed.
"""

import glob
import os
import platform
import subprocess
import time

from fans.generic_pwm import GPU_DRIVER_CHIPS

_HWMON = "sys/class/hwmon"
CANDIDATES = ("nct6775", "nct6683", "it87", "f71882fg", "w83627ehf")


def _read(path: str) -> str:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _default_run(command: list[str]):
    from controllers.detect import clean_env, resolve_bin

    argv = [resolve_bin(command[0]), *command[1:]]
    return subprocess.run(argv, capture_output=True, text=True, timeout=15, env=clean_env())


def board_fan_channels(root: str = "/") -> int:
    """Board fan channels with the full manual interface (pwm, mode and tach)."""
    count = 0
    for directory in sorted(glob.glob(os.path.join(root, _HWMON, "hwmon*"))):
        if _read(os.path.join(directory, "name")) in GPU_DRIVER_CHIPS:
            continue
        for enable in glob.glob(os.path.join(directory, "pwm[0-9]*_enable")):
            index = os.path.basename(enable)[len("pwm"):-len("_enable")]
            if all(os.path.exists(os.path.join(directory, leaf))
                   for leaf in (f"pwm{index}", f"fan{index}_input")):
                count += 1
    return count


def loaded_modules(root: str = "/") -> list[str]:
    return [name for name in CANDIDATES
            if os.path.isdir(os.path.join(root, "sys/module", name))]


def available_modules(root: str = "/", release: str | None = None) -> list[str]:
    release = release or platform.release()
    base = os.path.join(root, "lib/modules", release)
    builtin = _read(os.path.join(base, "modules.builtin"))
    found = []
    for name in CANDIDATES:
        shipped = glob.glob(os.path.join(base, "kernel/drivers/hwmon", f"{name}.ko*"))
        if shipped or f"/{name}.ko" in builtin or os.path.isdir(
                os.path.join(root, "sys/module", name)):
            found.append(name)
    return found


class BoardFanDriver:
    def __init__(self, root: str = "/", run=_default_run, release: str | None = None,
                 settle_s: float = 1.5, owned: tuple = ()) -> None:
        self._root = root
        self._run = run
        self._release = release
        self._settle_s = settle_s
        # A module this plugin loaded before a restart in the same boot stays ours.
        self._loaded_by_us: list[str] = [name for name in owned if name in CANDIDATES]
        self.last: dict | None = None

    def state(self) -> dict:
        return {
            "available": available_modules(self._root, self._release),
            "loaded": loaded_modules(self._root),
            "loaded_by_panel": list(self._loaded_by_us),
            "channels": board_fan_channels(self._root),
            "last": dict(self.last) if self.last else None,
        }

    def _wait_for_channels(self) -> int:
        deadline = time.monotonic() + self._settle_s
        while True:
            channels = board_fan_channels(self._root)
            if channels or time.monotonic() >= deadline:
                return channels
            time.sleep(0.1)

    @property
    def active_module(self) -> str | None:
        return self._loaded_by_us[-1] if self._loaded_by_us else None

    def load(self, only: str | None = None) -> dict:
        """Try each shipped candidate (or just `only`) until one publishes board fan
        channels. Modules that load without exposing a fan are unloaded again."""
        attempts = []
        channels = board_fan_channels(self._root)
        if channels:
            self.last = {"action": "load", "ok": True, "channels": channels,
                         "attempts": attempts, "detail": "already_present"}
            return self.state()
        already = set(loaded_modules(self._root))
        candidates = [name for name in available_modules(self._root, self._release)
                      if only is None or name == only]
        for name in candidates:
            if name in already:
                attempts.append({"module": name, "result": "already_loaded"})
                continue
            try:
                result = self._run(["modprobe", name])
                code = result.returncode
            except Exception as exc:  # noqa: BLE001
                attempts.append({"module": name, "result": type(exc).__name__})
                continue
            if code != 0:
                attempts.append({"module": name, "result": f"exit_{code}"})
                continue
            channels = self._wait_for_channels()
            if channels:
                if name not in self._loaded_by_us:
                    self._loaded_by_us.append(name)
                attempts.append({"module": name, "result": "fans", "channels": channels})
                break
            attempts.append({"module": name, "result": "no_fans"})
            self._unload(name)
        self.last = {"action": "load", "ok": channels > 0, "channels": channels,
                     "attempts": attempts,
                     "detail": "fans_found" if channels else "no_board_fans"}
        return self.state()

    def _unload(self, name: str) -> bool:
        try:
            return self._run(["modprobe", "-r", name]).returncode == 0
        except Exception:  # noqa: BLE001
            return False

    def release_failed(self) -> dict:
        self.last = {"action": "unload", "ok": False,
                     "channels": board_fan_channels(self._root), "attempts": [],
                     "detail": "fans_not_released"}
        return self.state()

    def unload(self) -> dict:
        results = {name: self._unload(name) for name in self._loaded_by_us}
        self._loaded_by_us = [name for name, ok in results.items() if not ok]
        self.last = {"action": "unload", "ok": all(results.values()),
                     "channels": board_fan_channels(self._root),
                     "attempts": [{"module": n, "result": "unloaded" if ok else "busy"}
                                  for n, ok in results.items()],
                     "detail": "unloaded" if all(results.values()) else "unload_failed"}
        return self.state()
