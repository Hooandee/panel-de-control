import glob
import os


def _read_int(path: str):
    try:
        with open(path) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _write(path: str, value: int) -> bool:
    try:
        with open(path, "w") as handle:
            handle.write(str(value))
        return True
    except OSError:
        return False


class AmdGpuPowerCap:
    """Standard amdgpu TGP cap with exact bounds, readback and restoration."""

    def __init__(self, root: str = "/", device_key: str | None = None) -> None:
        self._root = root
        self._device_key = device_key
        self._dir = self._find()
        self._captured_uw = None

    def _find(self):
        if self._device_key not in (None, "steam_machine"):
            return None
        pattern = os.path.join(self._root, "sys/class/hwmon/hwmon*")
        for directory in sorted(glob.glob(pattern)):
            try:
                with open(os.path.join(directory, "name")) as handle:
                    name = handle.read().strip()
            except OSError:
                continue
            required = ("power1_cap", "power1_cap_min", "power1_cap_max")
            if name == "amdgpu" and all(os.path.exists(os.path.join(directory, leaf)) for leaf in required):
                return directory
        return None

    @property
    def supported(self) -> bool:
        return self._dir is not None

    def _value(self, leaf):
        return _read_int(os.path.join(self._dir, leaf)) if self._dir else None

    @staticmethod
    def _watts(value):
        return None if value is None else round(value / 1_000_000)

    def state(self) -> dict:
        if not self.supported:
            return {"supported": False, "current_w": None, "min_w": None,
                    "max_w": None, "default_w": None}
        return {
            "supported": True,
            "current_w": self._watts(self._value("power1_cap")),
            "min_w": self._watts(self._value("power1_cap_min")),
            "max_w": self._watts(self._value("power1_cap_max")),
            "default_w": self._watts(self._value("power1_cap_default")),
        }

    def capture(self):
        return self._value("power1_cap") if self.supported else None

    def set_watts(self, watts: int) -> dict:
        state = self.state()
        if not state["supported"]:
            return {"ok": False, "requested_w": watts, "applied_w": None,
                    "detail": "amdgpu power cap unavailable"}
        requested = int(watts)
        target = max(state["min_w"], min(state["max_w"], requested))
        current = self._value("power1_cap")
        if self._captured_uw is None:
            self._captured_uw = current
        path = os.path.join(self._dir, "power1_cap")
        wrote = _write(path, target * 1_000_000)
        applied = self._watts(_read_int(path))
        ok = wrote and applied == target
        return {"ok": ok, "requested_w": requested, "applied_w": applied,
                "detail": "applied" if ok else "power cap readback mismatch"}

    def restore(self, target_uw=None) -> dict:
        if not self.supported:
            return {"ok": False, "applied_w": None, "detail": "amdgpu power cap unavailable"}
        target = target_uw if target_uw is not None else self._captured_uw
        if target is None:
            target = self._value("power1_cap_default")
        if target is None:
            return {"ok": False, "applied_w": None, "detail": "no restorable power cap"}
        path = os.path.join(self._dir, "power1_cap")
        wrote = _write(path, target)
        readback = _read_int(path)
        ok = wrote and readback == target
        if ok:
            self._captured_uw = None
        return {"ok": ok, "applied_w": self._watts(readback),
                "detail": "restored" if ok else "power cap restore mismatch"}
