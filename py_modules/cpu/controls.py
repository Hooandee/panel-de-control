import glob
import os
import re

from sysfs import read_int, read_str, write_str

_CPU = "sys/devices/system/cpu"


class SmtControl:
    """Simultaneous multi-threading via `cpu/smt/control` (on/off/forceoff/
    notsupported). Generic across AMD/Intel. Writing needs root; set() reads back
    to confirm."""

    def __init__(self, root="/"):
        self._path = os.path.join(root, _CPU, "smt", "control")
        val = read_str(self._path)
        self.supported = val is not None and val != "notsupported"

    def get(self):
        return read_str(self._path) if self.supported else None

    def enabled(self):
        return self.get() == "on"

    def set(self, enabled):
        if not self.supported:
            return False
        if not write_str(self._path, "on" if enabled else "off"):
            return False
        return self.enabled() == bool(enabled)


class _Boost:
    supported = False

    def enabled(self):
        return False

    def set(self, enabled):
        return False


class NullBoost(_Boost):
    """No CPU-boost interface on this device."""


class AmdBoost(_Boost):
    """AMD/acpi-cpufreq global boost: `cpu/cpufreq/boost` (1=on, 0=off)."""

    def __init__(self, root="/"):
        self._path = os.path.join(root, _CPU, "cpufreq", "boost")
        # Gate on a successful READ (not mere existence) so an unreadable node isn't
        # mis-reported as boost-off, matching SmtControl.
        self.supported = read_int(self._path) is not None

    def enabled(self):
        return read_int(self._path) == 1

    def set(self, enabled):
        if not self.supported:
            return False
        if not write_str(self._path, 1 if enabled else 0):
            return False
        return self.enabled() == bool(enabled)


class IntelBoost(_Boost):
    """Intel P-state turbo: `cpu/intel_pstate/no_turbo` (INVERTED — no_turbo=0 means
    boost ON)."""

    def __init__(self, root="/"):
        self._path = os.path.join(root, _CPU, "intel_pstate", "no_turbo")
        self.supported = read_int(self._path) is not None

    def enabled(self):
        return read_int(self._path) == 0

    def set(self, enabled):
        if not self.supported:
            return False
        if not write_str(self._path, 0 if enabled else 1):
            return False
        return self.enabled() == bool(enabled)


def select_boost(root="/"):
    """Pick the CPU-boost strategy: AMD cpufreq/boost, else Intel no_turbo, else Null."""
    for backend in (AmdBoost(root), IntelBoost(root)):
        if backend.supported:
            return backend
    return NullBoost()


class CoreControl:
    """Number of active PHYSICAL cores via `cpuN/online`. Cores are grouped by
    `topology/core_id` (SMT siblings share one), so this counts/keeps whole cores,
    independent of the SMT toggle. cpu0 has no `online` node (the kernel forbids
    offlining it) → its core is always kept, so the minimum is 1 core.

    Writing needs root. `set()` reads the result back: if the kernel clamps a write,
    the reported active count reflects reality, not the request."""

    def __init__(self, root="/"):
        self._base = os.path.join(root, _CPU)
        # Bring every offlined CPU back first: the kernel drops the topology of an offline
        # CPU, so a prior core-limit would make the map (and max_cores) reflect only the
        # online subset. Online all → read the true hardware topology → _apply_cpu
        # re-applies any saved limit afterwards.
        self._online_all_present()
        # {core_id: [cpu_index, ...]} ordered by core_id (lowest = kept first).
        self._cores = self._map()
        self.max_cores = len(self._cores) or None
        # Toggleable only if there's more than one core AND at least one online node
        # to write (cpu0-only trees expose nothing to change).
        self.supported = bool(self.max_cores and self.max_cores > 1
                              and glob.glob(os.path.join(self._base, "cpu[0-9]*", "online")))

    def _online_all_present(self):
        """Write 1 to every offlined cpuN/online node (cpu0 has none — always online)."""
        for p in glob.glob(os.path.join(self._base, "cpu[0-9]*", "online")):
            if read_int(p) == 0:
                write_str(p, 1)

    def _map(self):
        m = {}
        for p in glob.glob(os.path.join(self._base, "cpu[0-9]*", "topology", "core_id")):
            match = re.search(r"cpu(\d+)", p)
            cid = read_int(p)
            if match and cid is not None:
                m.setdefault(cid, []).append(int(match.group(1)))
        return dict(sorted(m.items()))

    def _online_path(self, idx):
        return os.path.join(self._base, f"cpu{idx}", "online")

    def _is_online(self, idx):
        v = read_int(self._online_path(idx))
        return True if v is None else v == 1  # no node (cpu0) => always online

    def active(self):
        """Count physical cores with at least one online logical CPU."""
        return sum(1 for idxs in self._cores.values()
                   if any(self._is_online(i) for i in idxs))

    def set(self, n):
        if not self.supported:
            return False
        n = max(1, min(self.max_cores, int(n)))  # always keep cpu0's core
        for pos, idxs in enumerate(self._cores.values()):
            want_on = pos < n
            for i in idxs:
                write_str(self._online_path(i), 1 if want_on else 0)  # cpu0 no-node write no-ops
        return self.active() == n
