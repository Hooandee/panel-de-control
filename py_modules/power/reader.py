import glob
import os


class PowerReader:
    """Reads actual APU/GPU power draw in watts from hwmon. AMD: the `amdgpu`
    hwmon chip exposes power1_average / power1_input in microwatts. Never raises;
    returns None when no source is available (honest 'unknown')."""

    def __init__(self, root="/"):
        self._root = root

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _amdgpu_dir(self):
        base = os.path.join(self._root, "sys/class/hwmon")
        for h in sorted(glob.glob(os.path.join(base, "hwmon*"))):
            try:
                with open(os.path.join(h, "name")) as f:
                    if f.read().strip() == "amdgpu":
                        return h
            except OSError:
                continue
        return None

    def read_watts(self):
        """Actual power draw in watts (float, 1 decimal), or None if unavailable."""
        d = self._amdgpu_dir()
        if d is None:
            return None
        for leaf in ("power1_average", "power1_input"):
            uw = self._read_int(os.path.join(d, leaf))
            if uw is not None and uw > 0:
                return round(uw / 1_000_000, 1)
        return None

    def read(self):
        return {"watts": self.read_watts()}
