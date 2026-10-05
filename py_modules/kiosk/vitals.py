"""Live clocks and memory for the bottom screen: what the chip is doing right now, not its limits."""

import glob
import os


def _read_int(path: str) -> int | None:
    try:
        with open(path) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def cpu_mhz(root: str = "/") -> int | None:
    """Fastest cluster's current clock; that is the one a game is waiting on."""
    clocks = [
        khz
        for path in glob.glob(os.path.join(root, "sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq"))
        if (khz := _read_int(path))
    ]
    return round(max(clocks) / 1000) if clocks else None


def gpu_mhz(root: str = "/") -> int | None:
    # ARM (Adreno/Mali) devfreq in Hz, then amdgpu hwmon in Hz, then Intel gt in MHz.
    for path in sorted(glob.glob(os.path.join(root, "sys/class/devfreq/*.gpu/cur_freq"))):
        if (hz := _read_int(path)) is not None:
            return round(hz / 1_000_000)
    for path in sorted(glob.glob(os.path.join(root, "sys/class/drm/card*/device/hwmon/hwmon*/freq1_input"))):
        if (hz := _read_int(path)) is not None:
            return round(hz / 1_000_000)
    for path in sorted(glob.glob(os.path.join(root, "sys/class/drm/card*/gt_act_freq_mhz"))):
        if (mhz := _read_int(path)) is not None:
            return mhz
    return None


def memory_gb(root: str = "/") -> tuple[float, float] | None:
    """(used, total) in GiB, where used = total minus what the kernel says is available."""
    values: dict[str, int] = {}
    try:
        with open(os.path.join(root, "proc/meminfo")) as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(rest.split()[0])
    except (OSError, ValueError, IndexError):
        return None
    if len(values) < 2:
        return None
    gib = 1024 * 1024
    total = values["MemTotal"] / gib
    return round(total - values["MemAvailable"] / gib, 2), round(total, 1)


def read(root: str = "/") -> dict:
    memory = memory_gb(root)
    return {
        "cpu_mhz": cpu_mhz(root),
        "gpu_mhz": gpu_mhz(root),
        "ram_used_gb": memory[0] if memory else None,
        "ram_total_gb": memory[1] if memory else None,
    }
