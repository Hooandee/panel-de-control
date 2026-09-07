import glob
import os
import time


class PowerReader:
    """Reads actual APU/GPU power draw in watts and GPU utilisation from sysfs.

    AMD: `amdgpu` hwmon exposes power1_average / power1_input in microwatts;
    `gpu_busy_percent` is under the DRM card device node. Never raises; returns
    None for any field that is unavailable (honest 'unknown').

    Sysfs paths are resolved once at construction and cached. If a cached path
    is absent at read time (e.g. module loaded later) the lookup is retried.

    `gpu_busy_percent` on some APUs (notably the Steam Deck's Van Gogh) is an
    INSTANTANEOUS sample of a tiny window that swings wildly 0<->100. A single
    read is unrepresentative (a ~30% game reads e.g. 0,0,0,100,100,0,...
    averaging ~22). read_gpu_busy() therefore sub-samples a short
    burst and returns the arithmetic mean — the honest time-average of GPU
    utilisation (mangohud does the same). The mean, not a percentile: `decide`
    already owns the up/down asymmetry (recent-peak up, smoothed-mean down)
    across its outer window; biasing this reading upward would corrupt both
    branches. Cheap: ~12 microsecond sysfs reads over ~120 ms vs a 2 s loop."""

    def __init__(self, root="/", gpu_samples=12, gpu_sample_gap=0.01):
        self._root = root
        self._gpu_samples = max(1, gpu_samples)
        self._gpu_sample_gap = max(0.0, gpu_sample_gap)
        self._amdgpu_hwmon = self._find_amdgpu_dir()
        self._gpu_busy_path = self._find_gpu_busy_path()
        (
            self._desktop_hwmon,
            self._desktop_gpu_device,
        ) = self._find_desktop_gpu_sources()

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _amdgpu_dirs(self) -> list[str]:
        base = os.path.join(self._root, "sys/class/hwmon")
        directories = []
        for h in sorted(glob.glob(os.path.join(base, "hwmon*"))):
            try:
                with open(os.path.join(h, "name")) as f:
                    if f.read().strip() == "amdgpu":
                        directories.append(h)
            except OSError:
                continue
        return directories

    def _drm_device_dirs(self) -> list[str]:
        pattern = os.path.join(self._root, "sys/class/drm/card*/device")
        return [
            path
            for path in sorted(glob.glob(pattern))
            if os.path.exists(path)
            and os.path.basename(os.path.dirname(path))[4:].isdigit()
        ]

    def _find_amdgpu_dir(self) -> str | None:
        directories = self._amdgpu_dirs()
        return directories[0] if directories else None

    def _find_gpu_busy_path(self) -> str | None:
        paths = [
            os.path.join(directory, "gpu_busy_percent")
            for directory in self._drm_device_dirs()
            if os.path.exists(os.path.join(directory, "gpu_busy_percent"))
        ]
        return paths[0] if paths else None

    @staticmethod
    def _has_power_cap(directory: str) -> bool:
        return all(
            os.path.exists(os.path.join(directory, leaf))
            for leaf in ("power1_cap", "power1_cap_min", "power1_cap_max")
        )

    def _find_desktop_gpu_sources(self) -> tuple[str | None, str | None]:
        hwmons = self._amdgpu_dirs()
        drm_devices = self._drm_device_dirs()
        drm_by_identity = {
            os.path.realpath(directory): directory for directory in drm_devices
        }
        correlated = []
        for hwmon in hwmons:
            device = os.path.join(hwmon, "device")
            if not os.path.exists(device):
                continue
            drm = drm_by_identity.get(os.path.realpath(device))
            if drm is not None:
                correlated.append((hwmon, drm))

        cap_candidates = [
            pair for pair in correlated if self._has_power_cap(pair[0])
        ]
        if len(cap_candidates) == 1:
            return cap_candidates[0]
        if len(cap_candidates) > 1 or len(correlated) > 1:
            return None, None
        if len(correlated) == 1:
            return correlated[0]
        return None, None

    def _refresh_desktop_gpu_sources(self) -> None:
        (
            self._desktop_hwmon,
            self._desktop_gpu_device,
        ) = self._find_desktop_gpu_sources()

    def _read_watts_from(self, directory):
        if directory is None:
            return None
        for leaf in ("power1_average", "power1_input"):
            uw = self._read_int(os.path.join(directory, leaf))
            if uw is not None and uw > 0:
                return round(uw / 1_000_000, 1)
        return None

    def read_watts(self):
        """Actual power draw in watts (float, 1 decimal), or None if unavailable."""
        if self._amdgpu_hwmon is None or not os.path.isdir(self._amdgpu_hwmon):
            self._amdgpu_hwmon = self._find_amdgpu_dir()
        return self._read_watts_from(self._amdgpu_hwmon)

    def _read_gpu_busy_from(self, path):
        if path is None:
            return None
        valid = []
        for i in range(self._gpu_samples):
            raw = self._read_int(path)
            if raw is not None:
                valid.append(max(0, min(raw, 100)))
            if self._gpu_sample_gap and i < self._gpu_samples - 1:
                time.sleep(self._gpu_sample_gap)
        if not valid:
            return None
        return round(sum(valid) / len(valid))

    def read_gpu_busy(self):
        """GPU utilisation as an integer percent (0–100), or None if unavailable.

        Sub-samples a short burst and returns the mean of the valid reads, to
        de-noise the instantaneous sensor (see class docstring). Honest: returns
        None only if EVERY read failed (never fabricates a 0)."""
        if self._gpu_busy_path is None or not os.path.exists(self._gpu_busy_path):
            self._gpu_busy_path = self._find_gpu_busy_path()
        return self._read_gpu_busy_from(self._gpu_busy_path)

    def read(self):
        return {"watts": self.read_watts(), "gpu_busy": self.read_gpu_busy()}

    def _hwmon_mhz(self, leaf):
        if self._desktop_hwmon is None:
            return None
        hz = self._read_int(os.path.join(self._desktop_hwmon, leaf))
        return None if hz is None else round(hz / 1_000_000)

    def _vram_mb(self, leaf):
        directory = self._desktop_gpu_device
        value = self._read_int(os.path.join(directory, leaf)) if directory else None
        return None if value is None else round(value / (1024 * 1024))

    def read_desktop(self, device_key=None):
        """Explicit dual-domain snapshot; CPU package power remains unknown unless
        the host exposes a trustworthy separate source (none is guessed here)."""
        if device_key not in (None, "steam_machine"):
            return {
                "cpu_watts": None,
                "gpu_watts": None,
                "gpu_busy": None,
                "gpu_clock_mhz": None,
                "gpu_clock_max_mhz": None,
                "vram_used_mb": None,
                "vram_total_mb": None,
            }
        if (
            self._desktop_hwmon is None
            or not os.path.isdir(self._desktop_hwmon)
            or self._desktop_gpu_device is None
            or not os.path.isdir(self._desktop_gpu_device)
        ):
            self._refresh_desktop_gpu_sources()
        busy_path = (
            os.path.join(self._desktop_gpu_device, "gpu_busy_percent")
            if self._desktop_gpu_device is not None
            else None
        )
        return {
            "cpu_watts": None,
            "gpu_watts": self._read_watts_from(self._desktop_hwmon),
            "gpu_busy": self._read_gpu_busy_from(busy_path),
            "gpu_clock_mhz": self._hwmon_mhz("freq1_input"),
            "gpu_clock_max_mhz": self._hwmon_mhz("freq1_max"),
            "vram_used_mb": self._vram_mb("mem_info_vram_used"),
            "vram_total_mb": self._vram_mb("mem_info_vram_total"),
        }
