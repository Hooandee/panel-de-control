"""PlayStation 5 console extras: the indicator light, the chassis buzzer, the SSD
temperature and the thermal guard state. Firmware nodes share one FirmwareIo with the
fan, which tracks each node separately."""
import glob
import os

from ps5.firmware_io import FirmwareIo
from ps5.led import Ps5Led
from ps5.thermal import ThermalGuard

BUZZER_BEEP = "sys/class/misc/ps5_buzzer/beep"
# drivers/ps5/buzzer.c: 0 silent, 1 short, 2 error, 3 long.
BEEP_ERROR = 2


class Ps5Console:
    def __init__(self, root: str = "/", io: FirmwareIo | None = None) -> None:
        self._root = root
        self.io = io or FirmwareIo()
        self.led = Ps5Led(root, self.io)
        self.guard = ThermalGuard()
        self._buzzer = os.path.join(root, BUZZER_BEEP)
        self._ssd_input: str | None = None
        self.last_beep: str | None = None

    @property
    def buzzer_supported(self) -> bool:
        return os.path.exists(self._buzzer)

    def beep(self) -> bool:
        error = self.io.write(self._buzzer, BEEP_ERROR) if self.buzzer_supported else "unsupported"
        self.last_beep = error or "sent"
        return error is None

    def ssd_celsius(self) -> float | None:
        if self._ssd_input is None or not os.path.exists(self._ssd_input):
            self._ssd_input = next((
                os.path.join(os.path.dirname(name), "temp1_input")
                for name in sorted(glob.glob(os.path.join(self._root, "sys/class/hwmon/hwmon*/name")))
                if _read(name) == "nvme"
            ), None)
        raw = _read(self._ssd_input) if self._ssd_input else None
        return int(raw) / 1000 if raw and raw.lstrip("-").isdigit() else None


def _read(path: str) -> str | None:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return None
