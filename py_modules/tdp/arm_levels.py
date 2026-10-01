import glob
import os

from sysfs import read_int, read_str, write_str
from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_CPUFREQ = "sys/devices/system/cpu/cpufreq"
_DEVFREQ = "sys/class/devfreq"
_LEVELS = 10
_FLOOR = 0.4


def _table(path, *names):
    values = set()
    for name in names:
        text = read_str(os.path.join(path, name)) or ""
        values.update(int(item) for item in text.split() if item.isdigit())
    return tuple(sorted(values))


def _snap_down(table, target):
    return max((value for value in table if value <= target), default=table[0])


class _Domain:
    def __init__(self, path, table, max_node, min_node, cpu):
        self.path = path
        self.cpu = cpu
        self.table = table
        self.max_node = os.path.join(path, max_node)
        self.min_node = os.path.join(path, min_node)

    def ceiling(self, level):
        fraction = _FLOOR + (1 - _FLOOR) * (level - 1) / (_LEVELS - 1)
        return _snap_down(self.table, int(self.table[-1] * fraction))

    def read(self):
        return read_int(self.max_node), read_int(self.min_node)

    def write(self, ceiling, floor=None):
        current_min = read_int(self.min_node)
        if current_min is None:
            return False
        floor = min(current_min, ceiling) if floor is None else floor
        if floor < current_min and not write_str(self.min_node, floor):
            return False
        if not write_str(self.max_node, ceiling):
            return False
        return floor == current_min or write_str(self.min_node, floor)


class ArmPerformanceLevels(TDPBackend):
    """Performance levels for ARM SoCs: each level caps every cpufreq cluster and the
    devfreq GPU at the same share of its own maximum, snapped to real table steps."""

    name = "arm-frequency-levels"
    unit = "level"
    auto_tdp_supported = False
    guard_interval_s = 3.0

    def __init__(self, root="/"):
        self._domains = []
        for path in sorted(glob.glob(os.path.join(root, _CPUFREQ, "policy[0-9]*")),
                           key=lambda p: int(os.path.basename(p)[6:])):
            table = _table(path, "scaling_available_frequencies", "scaling_boost_frequencies")
            if table:
                self._domains.append(_Domain(path, table, "scaling_max_freq", "scaling_min_freq", True))
        for path in sorted(glob.glob(os.path.join(root, _DEVFREQ, "*.gpu"))):
            table = _table(path, "available_frequencies")
            if table:
                self._domains.append(_Domain(path, table, "max_freq", "min_freq", False))
                break
        self._baseline = None

    @property
    def supported(self):
        return any(domain.cpu for domain in self._domains) and all(
            os.access(domain.max_node, os.W_OK) and os.access(domain.min_node, os.W_OK)
            for domain in self._domains
        )

    def get_limits(self):
        return TdpLimits(min_w=1, default_w=6, max_w=_LEVELS, max_ac_w=_LEVELS)

    def ceilings(self, level):
        return [domain.ceiling(level) for domain in self._domains]

    def level_table(self):
        table = {}
        for level in range(1, _LEVELS + 1):
            ceilings = self.ceilings(level)
            table[str(level)] = {
                "cpu_khz": [c for d, c in zip(self._domains, ceilings) if d.cpu],
                "gpu_mhz": next(
                    (c // 1_000_000 for d, c in zip(self._domains, ceilings) if not d.cpu),
                    None,
                ),
            }
        return table

    def read_applied(self):
        observed = [domain.read()[0] for domain in self._domains]
        for level in range(_LEVELS, 0, -1):
            if observed == self.ceilings(level):
                return level
        return None

    def set_tdp(self, watts, ac):
        level = max(1, min(_LEVELS, int(watts)))
        if not self.supported:
            return TdpResult(level, None, False, "arm levels unsupported")
        if self._baseline is None:
            self._baseline = [domain.read() for domain in self._domains]
        for domain, ceiling in zip(self._domains, self.ceilings(level)):
            if not domain.write(ceiling):
                return TdpResult(level, self.read_applied(), False, "write failed",
                                 failure_kind="write")
        applied = self.read_applied()
        if applied != level:
            return TdpResult(level, applied, False, "readback mismatch",
                             failure_kind="readback")
        return TdpResult(level, applied, True, "")

    def release(self):
        if self._baseline is None:
            return True
        ok = all(
            maximum is not None and minimum is not None and domain.write(maximum, minimum)
            for domain, (maximum, minimum) in zip(self._domains, self._baseline)
        )
        if ok:
            self._baseline = None
        return ok
