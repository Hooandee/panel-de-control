"""PlayStation 5 fan: the ps5-linux kernel exposes only the ICC autoservo target
temperature of the main SoC zone. The firmware drives the fan to hold it; Linux has
no PWM, RPM or tachometer for this fan, so the target is the only lever and the
only readback."""
import os
import time

from ps5.firmware_io import FirmwareIo

NODE = "sys/bus/platform/devices/ps5-fan/target_temp"
# The driver writes 80 °C at probe; that is the console's own behaviour.
FIRMWARE_DEFAULT_C = 80
MIN_C = 50
MAX_C = 90
PRESETS = (("quiet", 85), ("balanced", FIRMWARE_DEFAULT_C), ("cool", 70), ("max", MIN_C))
# Every read is a firmware round trip; the UI refreshes far more often than this.
READ_REFRESH_S = 10.0


def clamp_target(celsius) -> int:
    return max(MIN_C, min(MAX_C, int(celsius)))


class Ps5FanTarget:
    def __init__(self, root: str = "/", io: FirmwareIo | None = None,
                 clock=time.monotonic) -> None:
        self._path = os.path.join(root, NODE)
        self._io = io or FirmwareIo()
        self._clock = clock
        self._cached: int | None = None
        self._read_at: float | None = None
        self.last_result: dict | None = None

    @property
    def supported(self) -> bool:
        return os.path.isfile(self._path)

    def read(self, fresh: bool = False):
        if not self.supported:
            return None
        now = self._clock()
        if fresh or self._read_at is None or now - self._read_at >= READ_REFRESH_S:
            raw, error = self._io.read(self._path)
            self._read_at = now
            self._cached = int(raw) if error is None and raw and raw.isdigit() else None
        return self._cached

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
            return self._result(False, None, "unsupported")
        target = clamp_target(celsius)
        error = self._io.write(self._path, target)
        if error is not None:
            return self._result(False, self.read(fresh=True), error)
        held = self.read(fresh=True)
        if held != target:
            return self._result(False, held, "readback_mismatch")
        return self._result(True, held, "applied")

    def release(self) -> dict:
        return self.apply(FIRMWARE_DEFAULT_C)

    def _result(self, ok: bool, celsius, detail: str) -> dict:
        self.last_result = {"ok": ok, "celsius": celsius, "detail": detail}
        return dict(self.last_result)

    def diagnostics(self) -> dict:
        return {"last_result": self.last_result, "io": self._io.diagnostics()}
