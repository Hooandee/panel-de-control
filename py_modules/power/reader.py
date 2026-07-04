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
        self._amdgpu_hwmon: str | None = self._find_amdgpu_dir()
        self._gpu_busy_path: str | None = self._find_gpu_busy_path()

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _find_amdgpu_dir(self) -> str | None:
        base = os.path.join(self._root, "sys/class/hwmon")
        for h in sorted(glob.glob(os.path.join(base, "hwmon*"))):
            try:
                with open(os.path.join(h, "name")) as f:
                    if f.read().strip() == "amdgpu":
                        return h
            except OSError:
                continue
        return None

    def _find_gpu_busy_path(self) -> str | None:
        pattern = os.path.join(
            self._root, "sys/class/drm", "card*", "device", "gpu_busy_percent"
        )
        paths = sorted(glob.glob(pattern))
        return paths[0] if paths else None

    def read_watts(self):
        """Actual power draw in watts (float, 1 decimal), or None if unavailable."""
        if self._amdgpu_hwmon is None or not os.path.isdir(self._amdgpu_hwmon):
            self._amdgpu_hwmon = self._find_amdgpu_dir()
        d = self._amdgpu_hwmon
        if d is None:
            return None
        for leaf in ("power1_average", "power1_input"):
            uw = self._read_int(os.path.join(d, leaf))
            if uw is not None and uw > 0:
                return round(uw / 1_000_000, 1)
        return None

    def read_gpu_busy(self):
        """GPU utilisation as an integer percent (0–100), or None if unavailable.

        Sub-samples a short burst and returns the mean of the valid reads, to
        de-noise the instantaneous sensor (see class docstring). Honest: returns
        None only if EVERY read failed (never fabricates a 0)."""
        if self._gpu_busy_path is None or not os.path.exists(self._gpu_busy_path):
            self._gpu_busy_path = self._find_gpu_busy_path()
        path = self._gpu_busy_path
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

    def read(self):
        return {"watts": self.read_watts(), "gpu_busy": self.read_gpu_busy()}
