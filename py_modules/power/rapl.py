import glob
import os
import time


class RaplPackagePower:
    """CPU package power in watts from the powercap RAPL energy counter.

    Intel handhelds have no amdgpu hwmon, so this is their package power source.
    `energy_uj` is root-only on current kernels (MangoHud, running as the user,
    reads 0 W there). Power is the counter delta over wall time between two reads;
    a read sooner than `_MIN_GAP_S` repeats the last result. The first read and an
    unreadable or reset counter return None, never a guess."""

    _MIN_GAP_S = 0.5
    _REPROBE_S = 60.0

    def __init__(self, root="/", clock=time.monotonic):
        self._root = root
        self._clock = clock
        self._domain = None
        self._last = None
        self._probe_at = float("-inf")
        self._watts = None

    def _find_domain(self):
        pattern = os.path.join(self._root, "sys/class/powercap/intel-rapl:*")
        for path in sorted(glob.glob(pattern)):
            if os.path.basename(path).count(":") != 1:
                continue
            try:
                with open(os.path.join(path, "name")) as handle:
                    if handle.read().strip().startswith("package"):
                        return path
            except OSError:
                continue
        return None

    @staticmethod
    def _read_int(path):
        try:
            with open(path) as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            return None

    def read(self):
        if self._domain is None:
            now = self._clock()
            if now < self._probe_at:
                return None
            self._probe_at = now + self._REPROBE_S
            self._domain = self._find_domain()
            if self._domain is None:
                return None
        energy = self._read_int(os.path.join(self._domain, "energy_uj"))
        now = self._clock()
        if energy is None:
            self._domain = None
            self._last = None
            return None
        previous = self._last
        if previous is not None and now - previous[1] < self._MIN_GAP_S:
            return self._watts
        self._last = (energy, now)
        if previous is None:
            return None
        delta_uj = energy - previous[0]
        if delta_uj < 0:
            wrap = self._read_int(os.path.join(self._domain, "max_energy_range_uj"))
            delta_uj = delta_uj + wrap if wrap else -1
        self._watts = (
            round(delta_uj / (now - previous[1]) / 1_000_000, 1) if delta_uj >= 0 else None
        )
        return self._watts
