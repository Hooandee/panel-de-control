"""PlayStation 5 console light (ps5-led driver): one LED class device per firmware
preset, `ps5:<preset>:indicator`. Writing a non-zero brightness sends that preset over
ICC; the driver skips a resend of the preset already shown, so replaying an animation
means switching it off first. The preset set differs between kernels, so it is always
read from sysfs, and `brightness` does not report what the light is showing."""
import os
import re

from ps5.firmware_io import FirmwareIo

LED_DIR = "sys/class/leds"
PREFIX = "ps5:"
SUFFIX = ":indicator"
OFF = "off"
# Breathe, pulse and transition presets play once in firmware.
_ANIMATED = re.compile(r"breathe|pulse|anim|sunrise|_to_")
_NAME = re.compile(r"^[a-z0-9_]+$")


def is_animated(preset: str) -> bool:
    return bool(_ANIMATED.search(preset))


class Ps5Led:
    def __init__(self, root: str = "/", io: FirmwareIo | None = None) -> None:
        self._dir = os.path.join(root, LED_DIR)
        self._io = io or FirmwareIo()
        self.last_result: dict | None = None

    def presets(self) -> list[str]:
        try:
            entries = os.listdir(self._dir)
        except OSError:
            return []
        names = {
            entry[len(PREFIX):-len(SUFFIX)]
            for entry in entries
            if entry.startswith(PREFIX) and entry.endswith(SUFFIX)
        }
        return sorted((name for name in names if _NAME.match(name)), key=lambda name: (name != OFF, name))

    @property
    def supported(self) -> bool:
        return bool(self.presets())

    def _brightness(self, preset: str) -> str:
        return os.path.join(self._dir, f"{PREFIX}{preset}{SUFFIX}", "brightness")

    def _missing(self, preset: str) -> str | None:
        # No ps5:* LED at all means the driver has not registered yet, not a renamed preset.
        presets = self.presets()
        if not presets:
            return "not_ready"
        return None if preset in presets else "unknown_preset"

    def apply(self, preset: str) -> dict:
        missing = self._missing(preset)
        if missing:
            return self._result(False, preset, missing)
        error = self._io.write(self._brightness(preset), 1)
        return self._result(error is None, preset, error or "sent")

    def replay(self, preset: str) -> dict:
        missing = self._missing(preset)
        if missing:
            return self._result(False, preset, missing)
        path = self._brightness(preset)
        error = self._io.write(path, 0) or self._io.write(path, 1)
        return self._result(error is None, preset, error or "replayed")

    def _result(self, ok: bool, preset: str, detail: str) -> dict:
        self.last_result = {"ok": ok, "preset": preset, "detail": detail}
        return dict(self.last_result)
