"""PlayStation 5 fan: the ps5-linux kernel exposes only the ICC autoservo target
temperature of the main SoC zone. The firmware drives the fan to hold it; Linux has
no PWM, RPM or tachometer for this fan, so the target is the only lever and the
only readback."""
import os

from sysfs import read_int, write_str

NODE = "sys/bus/platform/devices/ps5-fan/target_temp"
# The driver writes 80 °C at probe; that is the console's own behaviour.
FIRMWARE_DEFAULT_C = 80
MIN_C = 50
MAX_C = 90
PRESETS = (("quiet", 85), ("balanced", FIRMWARE_DEFAULT_C), ("cool", 70), ("max", MIN_C))


def clamp_target(celsius) -> int:
    return max(MIN_C, min(MAX_C, int(celsius)))


class Ps5FanTarget:
    name = "ps5_fan"

    def __init__(self, root: str = "/") -> None:
        self._path = os.path.join(root, NODE)

    @property
    def supported(self) -> bool:
        return os.path.isfile(self._path)

    def read(self):
        return read_int(self._path) if self.supported else None

    def state(self) -> dict:
        if not self.supported:
            return {"supported": False}
        return {
            "supported": True,
            "celsius": self.read(),
            "min": MIN_C,
            "max": MAX_C,
            "default": FIRMWARE_DEFAULT_C,
            "presets": [{"id": key, "celsius": value} for key, value in PRESETS],
        }

    def apply(self, celsius: int) -> dict:
        if not self.supported:
            return {"ok": False, "celsius": None, "detail": "unsupported"}
        target = clamp_target(celsius)
        if not write_str(self._path, target):
            return {"ok": False, "celsius": self.read(), "detail": "write_failed"}
        held = self.read()
        if held != target:
            return {"ok": False, "celsius": held, "detail": "readback_mismatch"}
        return {"ok": True, "celsius": held, "detail": "applied"}

    def release(self) -> dict:
        return self.apply(FIRMWARE_DEFAULT_C)
