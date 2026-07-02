import os

from sysfs import read_int, read_str, write_str

_CPU = "sys/devices/system/cpu"


class SmtControl:
    """Simultaneous multi-threading via `cpu/smt/control` (on/off/forceoff/
    notsupported). Generic across AMD/Intel. Writing needs root; set() reads back
    to confirm (never-fake)."""

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
        # mis-reported as boost-off (never-fake), matching SmtControl.
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
