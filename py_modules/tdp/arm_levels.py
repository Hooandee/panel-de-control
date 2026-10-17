import glob
import os
import time

from sysfs import read_int, read_str, write_str
from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_CPUFREQ = "sys/devices/system/cpu/cpufreq"
_DEVFREQ = "sys/class/devfreq"
_COOLING = "sys/class/thermal"
_LEVELS = 10
_FLOOR = 0.4
# SCMI cpufreq (SM8750) publishes a new scaling_max_freq a few hundred ms after the write.
_SETTLE_S = 0.6
_SETTLE_STEP_S = 0.05


def _values(path, name):
    text = read_str(os.path.join(path, name)) or ""
    return {int(item) for item in text.split() if item.isdigit()}


def _snap_down(table, target):
    return max((value for value in table if value <= target), default=table[0])


def _cooling_states(root):
    states = {}
    for device in glob.glob(os.path.join(root, _COOLING, "cooling_device*")):
        kind = read_str(os.path.join(device, "type"))
        state = read_int(os.path.join(device, "cur_state"))
        if kind and state is not None:
            states[kind] = state
    return states


def _boost_on(root):
    return read_str(os.path.join(root, _CPUFREQ, "boost")) != "0"


class _Domain:
    def __init__(self, root, path, cpu):
        self.root = root
        self.path = path
        self.cpu = cpu
        if cpu:
            self.max_node = os.path.join(path, "scaling_max_freq")
            self.min_node = os.path.join(path, "scaling_min_freq")
            self._base = _values(path, "scaling_available_frequencies")
            self._boost = _values(path, "scaling_boost_frequencies")
            first_cpu = (read_str(os.path.join(path, "related_cpus")) or "").split()
            self.cooling = f"cpufreq-cpu{first_cpu[0]}" if first_cpu else None
        else:
            self.max_node = os.path.join(path, "max_freq")
            self.min_node = os.path.join(path, "min_freq")
            self._base = _values(path, "available_frequencies")
            self._boost = set()
            self.cooling = f"devfreq-{os.path.basename(path)}"

    def table(self, boost_on=None):
        if boost_on is None:
            boost_on = _boost_on(self.root)
        values = self._base | (self._boost if boost_on else set())
        return tuple(sorted(values))

    def ceiling(self, level, boost_on=None):
        table = self.table(boost_on)
        fraction = _FLOOR + (1 - _FLOOR) * (level - 1) / (_LEVELS - 1)
        return _snap_down(table, int(table[-1] * fraction))

    def holds(self, ceiling, cooling_states, observed=None):
        if observed is None:
            observed = read_int(self.max_node)
        if observed == ceiling:
            return True
        # Thermal cooling lowers the effective limit below what was written.
        throttled = cooling_states.get(self.cooling, 0) > 0
        return throttled and observed is not None and observed <= ceiling

    def write(self, ceiling):
        current_min = read_int(self.min_node)
        if current_min is None:
            return False
        if current_min > ceiling and not write_str(self.min_node, self.table()[0]):
            return False
        return write_str(self.max_node, ceiling)


class ArmPerformanceLevels(TDPBackend):
    """Performance levels for ARM SoCs: each level caps every cpufreq cluster and the
    devfreq GPU at the same share of its own maximum, snapped to real table steps.
    A split GPU level caps the GPU on its own while the CPU keeps the requested level."""

    name = "arm-frequency-levels"
    unit = "level"
    auto_tdp_safe = True
    guard_interval_s = 3.0

    def __init__(self, root="/", on_release=None, sleep=time.sleep, clock=time.monotonic):
        self._root = root
        self._on_release = on_release
        self._sleep = sleep
        self._clock = clock
        self._gpu_level = None
        self._applied_gpu_level = None
        self._domains = []
        for path in sorted(glob.glob(os.path.join(root, _CPUFREQ, "policy[0-9]*")),
                           key=lambda p: int(os.path.basename(p)[6:])):
            domain = _Domain(root, path, cpu=True)
            if domain.table():
                self._domains.append(domain)
        for path in sorted(glob.glob(os.path.join(root, _DEVFREQ, "*.gpu"))):
            domain = _Domain(root, path, cpu=False)
            if domain.table():
                self._domains.append(domain)
                break

    @property
    def supported(self):
        return any(domain.cpu for domain in self._domains) and all(
            os.access(domain.max_node, os.W_OK) and os.access(domain.min_node, os.W_OK)
            for domain in self._domains
        )

    def get_limits(self):
        return TdpLimits(min_w=1, default_w=6, max_w=_LEVELS, max_ac_w=_LEVELS)

    @property
    def gpu_level_supported(self):
        return any(not domain.cpu for domain in self._domains)

    @property
    def split_gpu_level(self):
        return self._gpu_level

    @property
    def applied_split_gpu_level(self):
        """The split GPU level of the last write that settled, None when linked or unconfirmed."""
        return self._applied_gpu_level

    def split_gpu_drifted(self):
        """True when the CPU still holds a level but another writer moved the split GPU cap."""
        return (
            self._gpu_level is not None
            and self._held_level() is None
            and self._held_level(cpu_only=True) is not None
        )

    def set_split_gpu_level(self, level):
        self._gpu_level = None if level is None else max(1, min(_LEVELS, int(level)))

    def ceilings(self, level, boost_on=None):
        if boost_on is None:
            boost_on = _boost_on(self._root)
        return [domain.ceiling(level, boost_on) for domain in self._domains]

    def _target_ceilings(self, level, boost_on=None):
        if boost_on is None:
            boost_on = _boost_on(self._root)
        gpu_level = level if self._gpu_level is None else self._gpu_level
        return [
            domain.ceiling(level if domain.cpu else gpu_level, boost_on)
            for domain in self._domains
        ]

    def level_table(self):
        table = {}
        boost_on = _boost_on(self._root)
        for level in range(1, _LEVELS + 1):
            ceilings = self.ceilings(level, boost_on)
            table[str(level)] = {
                "cpu_khz": [c for d, c in zip(self._domains, ceilings) if d.cpu],
                "gpu_mhz": next(
                    (c // 1_000_000 for d, c in zip(self._domains, ceilings) if not d.cpu),
                    None,
                ),
            }
        return table

    def _holds(self, level, cooling_states):
        return all(
            domain.holds(ceiling, cooling_states)
            for domain, ceiling in zip(self._domains, self._target_ceilings(level))
        )

    def _settled(self, level):
        deadline = self._clock() + _SETTLE_S
        while not self._holds(level, _cooling_states(self._root)):
            if self._clock() >= deadline:
                return False
            self._sleep(_SETTLE_STEP_S)
        return True

    def _held_level(self, cpu_only=False):
        # Read each node once and match levels in memory: this runs on every power poll.
        cooling_states = _cooling_states(self._root)
        boost_on = _boost_on(self._root)
        domains = [domain for domain in self._domains if domain.cpu or not cpu_only]
        observed = [read_int(domain.max_node) for domain in domains]
        for level in range(_LEVELS, 0, -1):
            gpu_level = level if self._gpu_level is None else self._gpu_level
            if all(
                domain.holds(domain.ceiling(level if domain.cpu else gpu_level, boost_on),
                             cooling_states, seen)
                for domain, seen in zip(domains, observed)
            ):
                return level
        return None

    def read_applied(self):
        return self._held_level()

    def set_tdp(self, watts, ac):
        level = max(1, min(_LEVELS, int(watts)))
        self._applied_gpu_level = None
        if not self.supported:
            return TdpResult(level, None, False, "arm levels unsupported")
        for domain, ceiling in zip(self._domains, self._target_ceilings(level)):
            if not domain.write(ceiling):
                return TdpResult(level, self.read_applied(), False, "write failed",
                                 failure_kind="write")
        if not self._settled(level):
            return TdpResult(level, self.read_applied(), False, "readback mismatch",
                             failure_kind="readback")
        self._applied_gpu_level = self._gpu_level
        return TdpResult(level, level, True, "")

    def release(self):
        self._gpu_level = None
        self._applied_gpu_level = None
        ok = all(domain.write(domain.table()[-1]) for domain in self._domains)
        if self._on_release is not None:
            try:
                self._on_release()
            except Exception:  # noqa: BLE001
                pass
        return ok
