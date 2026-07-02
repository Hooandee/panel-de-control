import glob
import os

from sysfs import read_int, read_str

_CPU = "sys/devices/system/cpu"


def _count_range(spec):
    """Count CPUs in a sysfs range spec like "0-15" or "0-3,8-11". None if empty."""
    if not spec:
        return None
    n = 0
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            n += int(b) - int(a) + 1
        else:
            n += 1
    return n


def read_cpu_info(root="/"):
    """CPU topology + frequency range from sysfs (all static — resolve once). Never
    raises; every field is None when the kernel doesn't expose it (honest 'unknown').
    `cores` = distinct physical cores; `threads` = real logical CPUs (`present`), NOT
    an assumed cores×2 — Lunar Lake (MSI Claw) has no hyperthreading, so threads ==
    cores there."""
    base = os.path.join(root, _CPU)

    core_ids = set()
    for p in glob.glob(os.path.join(base, "cpu[0-9]*", "topology", "core_id")):
        v = read_int(p)
        if v is not None:
            core_ids.add(v)

    return {
        "cores": len(core_ids) or None,
        "threads": _count_range(read_str(os.path.join(base, "present"))),
        "base_khz": read_int(os.path.join(base, "cpufreq/policy0/base_frequency")),
        "max_khz": read_int(os.path.join(base, "cpufreq/policy0/cpuinfo_max_freq")),
    }
