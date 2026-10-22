"""Live readings for panel scenes, plus the hysteresis that keeps them from re-rendering often."""

import glob
import os
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


class SystemMetrics:
    def __init__(self, root: Path | str = "/"):
        self._root = str(root)
        self._last_cpu: tuple[int, int] | None = None

    def _path(self, rel: str) -> str:
        return os.path.join(self._root, rel)

    def sample(self) -> dict:
        return {
            "cpu_pct": self._cpu_pct(),
            "ram_pct": self._ram_pct(),
            "gpu_pct": self._first_number("sys/class/drm/card*/device/gpu_busy_percent"),
            "gpu_w": self._gpu_watts(),
            "gpu_temp": self._first_temp("sys/class/drm/card*/device/hwmon/hwmon*/temp1_input"),
            "cpu_temp": self._cpu_temp(),
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
