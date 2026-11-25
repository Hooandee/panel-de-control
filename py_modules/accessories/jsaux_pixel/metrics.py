"""Live readings for panel scenes, plus the hysteresis that keeps them from re-rendering often."""

import glob
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path


def _read(path: str) -> str | None:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return None


def _number(path: str) -> float | None:
    raw = _read(path)
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


_MIN_SAMPLE_GAP_S = 0.8
# Valve's fan controller on the Steam Machine tops the system fan at 1800 RPM.
_SYSTEM_FANS = {"steamdeck_hwmon": 1800.0}


class SystemMetrics:
    """Thread-safe: callers less than a second apart share one reading, so a preview on another
    thread cannot shorten the CPU-load window the worker relies on."""

    def __init__(self, root: Path | str = "/", clock: Callable[[], float] = time.monotonic):
        self._root = str(root)
        self._clock = clock
        self._last_cpu: tuple[int, int] | None = None
        self._lock = threading.Lock()
        self._cached: tuple[float, dict] | None = None

    def _path(self, rel: str) -> str:
        return os.path.join(self._root, rel)

    def sample(self) -> dict:
        with self._lock:
            now = self._clock()
            if self._cached and now - self._cached[0] < _MIN_SAMPLE_GAP_S:
                return dict(self._cached[1])
            reading = self._read()
            self._cached = (now, reading)
            return dict(reading)

    def _read(self) -> dict:
        return {
            "cpu_pct": self._cpu_pct(),
            "ram_pct": self._ram_pct(),
            "gpu_pct": self._first_number("sys/class/drm/card*/device/gpu_busy_percent"),
            "gpu_w": self._gpu_watts(),
            "gpu_temp": self._first_temp("sys/class/drm/card*/device/hwmon/hwmon*/temp1_input"),
            "cpu_temp": self._cpu_temp(),
            "fan_pct": self._fan_share(),
        }

    def _cpu_pct(self) -> int | None:
        line = (_read(self._path("proc/stat")) or "").split("\n", 1)[0]
        fields = line.split()
        if len(fields) < 5 or fields[0] != "cpu":
            return None
        values = [int(v) for v in fields[1:] if v.isdigit()]
        idle, total = values[3] + (values[4] if len(values) > 4 else 0), sum(values)
        previous, self._last_cpu = self._last_cpu, (idle, total)
        if previous is None or total <= previous[1]:
            return None
        busy = 1 - (idle - previous[0]) / (total - previous[1])
        return max(0, min(100, round(busy * 100)))

    def _ram_pct(self) -> int | None:
        values = {}
        for line in (_read(self._path("proc/meminfo")) or "").splitlines():
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(rest.split()[0])
        if values.get("MemTotal"):
            return round(100 * (1 - values.get("MemAvailable", 0) / values["MemTotal"]))
        return None

    def _first_number(self, pattern: str) -> int | None:
        for path in sorted(glob.glob(self._path(pattern))):
            value = _number(path)
            if value is not None:
                return round(value)
        return None

    def _gpu_watts(self) -> float | None:
        for path in sorted(glob.glob(self._path("sys/class/drm/card*/device/hwmon/hwmon*/power1_average"))):
            value = _number(path)
            if value is not None:
                return round(value / 1_000_000, 1)
        return None

    def _first_temp(self, pattern: str) -> int | None:
        for path in sorted(glob.glob(self._path(pattern))):
            value = _number(path)
            if value is not None:
                return int(value // 1000)
        return None

    def _fan_share(self) -> float | None:
        """The system fan; the GPU hwmon channel reads 0 on the Steam Machine, so it is not used."""
        for name_path in sorted(glob.glob(self._path("sys/class/hwmon/hwmon*/name"))):
            cap = _SYSTEM_FANS.get(_read(name_path) or "")
            if cap is None:
                continue
            folder = os.path.dirname(name_path)
            rpm = _number(os.path.join(folder, "fan1_input"))
            limit = _number(os.path.join(folder, "fan1_max")) or cap
            if rpm is not None and limit > 0:
                return round(max(0.0, min(1.0, rpm / limit)), 2)
        return None

    def _cpu_temp(self) -> int | None:
        for name_path in sorted(glob.glob(self._path("sys/class/hwmon/hwmon*/name"))):
            if _read(name_path) in ("k10temp", "coretemp", "zenpower"):
                value = _number(os.path.join(os.path.dirname(name_path), "temp1_input"))
                if value is not None:
                    return int(value // 1000)
        return None


class Stepper:
    """Rounds a reading to steps and only moves once it clearly crosses into the next one."""

    def __init__(self, size: float, margin: float):
        self.size, self.margin = size, margin
        self.shown: float | None = None

    def __call__(self, value: float | None):
        if value is None:
            self.shown = None
            return None
        if self.shown is None or abs(value - self.shown) >= self.size / 2 + self.margin:
            stepped = round(value / self.size) * self.size
            self.shown = int(stepped) if float(stepped).is_integer() else stepped
        return self.shown
