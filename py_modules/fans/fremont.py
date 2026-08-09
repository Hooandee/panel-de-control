import asyncio
import glob
import os
import threading

from fans.control import _interp, _read, _read_int, _write, sanitize_curve

_HWMON = "sys/class/hwmon"
_INTERVAL = 1.5


class FremontFanBackend:
    """Valve Fremont's independent system-RPM and discrete-GPU PWM channels."""

    name = "fremont-dual-fan"
    resettable = True

    def __init__(self, temp_fn=None, root: str = "/") -> None:
        self._root = root
        self._system = self._find("steamdeck_hwmon", "fan1_target")
        self._gpu = self._find("amdgpu", "pwm1_enable")
        self._cpu_sensor = self._find("acpitz", "temp1_input")
        self._points = {"system": None, "gpu": None}
        self._lock = threading.RLock()
        self._task = None

    def _find(self, name, required):
        for directory in sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*"))):
            if (_read(os.path.join(directory, "name")) == name
                    and os.path.exists(os.path.join(directory, required))):
                return directory
        return None

    @property
    def supported(self) -> bool:
        return self._system is not None

    @property
    def _owns_fan(self) -> bool:
        return any(self._points.values())

    def _temp(self, key):
        if key == "system":
            values = []
            if self._cpu_sensor:
                values.append(_read_int(os.path.join(self._cpu_sensor, "temp1_input")))
            if self._gpu:
                values.extend([
                    _read_int(os.path.join(self._gpu, "temp2_input")),
                    _read_int(os.path.join(self._gpu, "temp3_input")),
                ])
            valid = [value for value in values if value is not None]
            return max(valid) / 1000 if valid else None
        return None

    def _apply_channel(self, key) -> bool:
        points = self._points.get(key)
        temp = self._temp(key)
        if not points or temp is None:
            self._release(key)
            return False
        pwm = max(0, min(255, _interp(points, temp)))
        if key == "system":
            target = round(pwm / 255 * 1800)
            path = os.path.join(self._system, "fan1_target")
            return _write(path, str(target)) and _read_int(path) == target
        return False

    def _release(self, key) -> bool:
        if key == "system":
            path = os.path.join(self._system, "fan1_target")
            return _write(path, "0") and _read_int(path) == 0
        return True

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        return {
            "supported": True,
            "source": self.name,
            "pwm_max": 255,
            "independent": True,
            "fans": [
                {"key": "system", "label": "System fan", "sensor": "CPU / GPU / VRAM",
                 "rpm": _read_int(os.path.join(self._system, "fan1_input")),
                 "max_rpm": 1800, "enable": 1 if self._points["system"] else 2,
                 "points": self._points["system"], "controllable": True},
                {"key": "gpu", "label": "GPU fan", "sensor": "GPU junction",
                 "rpm": _read_int(os.path.join(self._gpu, "fan1_input")),
                 "max_rpm": _read_int(os.path.join(self._gpu, "fan1_max")),
                 "enable": _read_int(os.path.join(self._gpu, "pwm1_enable")),
                 "points": None, "controllable": False},
            ] if self._gpu else [
                {"key": "system", "label": "System fan", "sensor": "CPU / GPU / VRAM",
                 "rpm": _read_int(os.path.join(self._system, "fan1_input")),
                 "max_rpm": 1800, "enable": 1 if self._points["system"] else 2,
                 "points": self._points["system"], "controllable": True},
            ],
        }

    def set_curve(self, fan_key: str, points: list) -> dict:
        if not self.supported or fan_key not in self._points:
            return {"ok": False, "detail": "Fremont fan channel unavailable"}
        if fan_key == "gpu":
            return {"ok": False, "detail": "Fremont GPU firmware rejects manual fan control"}
        with self._lock:
            self._points[fan_key] = [list(point) for point in sanitize_curve(points)]
            ok = self._apply_channel(fan_key)
        self.start()
        return {"ok": ok, "detail": f"{fan_key} curve applied" if ok else f"{fan_key} curve readback failed"}

    def apply_curve_all(self, points: list) -> dict:
        return self.set_curve("system", points)

    def set_auto(self, fan_key=None) -> dict:
        keys = (fan_key,) if fan_key else ("system", "gpu")
        if any(key not in self._points for key in keys):
            return {"ok": False, "detail": "unknown Fremont fan channel"}
        with self._lock:
            ok = True
            for key in keys:
                owned = self._points[key] is not None
                self._points[key] = None
                if owned:
                    ok = self._release(key) and ok
        return {"ok": ok, "detail": "channel(s) returned to previous owner"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)

    def start(self) -> None:
        if self._task is not None or not self._owns_fan:
            return
        try:
            self._task = asyncio.get_running_loop().create_task(self._loop())
        except RuntimeError:
            self._task = None

    async def _loop(self):
        try:
            while self._owns_fan:
                await asyncio.sleep(_INTERVAL)
                with self._lock:
                    for key in ("system",):
                        if self._points[key]:
                            self._apply_channel(key)
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
