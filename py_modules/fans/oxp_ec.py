"""OneXPlayer Apex fan control over the EC (opt-in, experimental).

The SteamOS 6.16 kernel ships ``oxpec`` without the Apex in its DMI table, so no
hwmon fan node exists there (it works on Bazzite's newer kernel). Until SteamOS
rebases, drive the fan through the EC using the map the driver documents for the
``oxp_fly`` board: ``0x4A`` mode (0=auto, 1=manual), ``0x4B`` duty (0-255, no
scaling), ``0x76``/``0x77`` RPM (16-bit big-endian, read-only).

Access is via ``ec_sys`` debugfs (byte offset == register), serialised by the kernel
ACPI EC lock. Writing needs ec_sys with ``write_support=1``; without it the backend
refuses control rather than reporting success. DMI-gated, and it stands down as soon
as an oxpec hwmon node appears (the generic pwm path then owns the fan).
"""

import glob
import os
from typing import Callable, Optional

from fans.control import _interp, _read
from fans.ec_io import EcSys
from fans.software_loop import SoftwareLoopBackend

# EC register map (oxp_fly board — source: drivers/platform/x86/oxpec.c).
REG_MODE = 0x4A
REG_DUTY = 0x4B
REG_RPM = 0x76  # 16-bit big-endian across 0x76 (high) and 0x77 (low)
MODE_AUTO = 0x00
MODE_MANUAL = 0x01

# Above this temperature the curve is ignored and the fan forced to full duty — a
# bad or lazy curve must never leave the fan slow while hot (mirrors the Go S guard).
_APEX_TEMP_GUARD_C = 90
_RELEASE_CONFIRM_RETRIES = 3

_DMI_MATCH_APEX = ("ONEXPLAYER APEX",)
# oxpec hwmon chip names — when one appears the kernel driver owns the fan and this
# raw-EC backend must stand down (generic pwm handles it).
_OXP_HWMON_NAMES = ("oxp_ec", "oxpec", "oxp-sensors")


def oxpec_hwmon_present(root: str = "/") -> bool:
    """True when the kernel exposes the oxpec hwmon fan node (pwm or fan input). When
    it does, the real driver owns the fan and the raw-EC path stands down — and the
    'kernel doesn't have the driver yet' UI note no longer applies."""
    for d in glob.glob(os.path.join(root, "sys/class/hwmon/hwmon*")):
        if (_read(os.path.join(d, "name")) or "") in _OXP_HWMON_NAMES:
            if os.path.exists(os.path.join(d, "pwm1")) or \
                    os.path.exists(os.path.join(d, "fan1_input")):
                return True
    return False


class OxpEcFanBackend(SoftwareLoopBackend):
    """OneXPlayer Apex EC fan control (opt-in, experimental). Duty-based (0x4B), with
    manual mode asserted at 0x4A. Confirmed by register readback (RPM does not
    reliably track a duty on these fans), with a high-temp guardian on top."""

    name = "oxp-apex-ec"
    min_rpm = 0
    max_rpm = 255  # the "target" IS the duty (0–255): base _duty_to_target is identity

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        self._ec = ec or EcSys(root=root)
        super().__init__(temp_fn=temp_fn, root=root)
        self._dmi_ok = self._dmi_matches()
        # The hwmon-vs-EC handoff can only flip on a kernel update (→ reboot → _init
        # re-runs), so probe once; supported is read on every monitor poll.
        self._hwmon_present = oxpec_hwmon_present(root)

    def _find_chip(self) -> Optional[str]:
        return None  # no hwmon node — support is DMI-based (see `supported`)

    @property
    def supported(self) -> bool:
        # Stand down if the kernel already exposes the oxpec hwmon fan node: the
        # generic pwm backend owns it then, so we never fight the real driver.
        return self._dmi_ok and not self._hwmon_present

    def _dmi_matches(self) -> bool:
        dmi = os.path.join(self._root, "sys/class/dmi/id")
        text = ((_read(os.path.join(dmi, "board_name")) or "") + " "
                + (_read(os.path.join(dmi, "product_name")) or "")).upper()
        return any(tok in text for tok in _DMI_MATCH_APEX)

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        """Curve → duty (0–255). Duty 0 is a valid quiet point (fan off but still in
        manual mode — NOT a firmware release, which goes through the mode register).
        Past the hard temp limit, force full duty regardless of the curve. None
        (writes nothing) when not driving."""
        if self._points is None or temp is None:
            return None
        if temp >= _APEX_TEMP_GUARD_C:
            return 255
        return self._duty_to_target(_interp(self._points, temp))

    def _before_drive(self) -> bool:
        # Take ownership only if the EC is actually writable on this kernel (this also
        # loads ec_sys with write support); honest False otherwise.
        return self._ec.writable()

    def _write_target(self, duty: int) -> bool:
        duty = max(0, min(255, int(duty)))
        # Assert manual mode before the duty (the EC only honours 0x4B in manual);
        # the write is idempotent and the loop re-asserts, so write it unconditionally.
        # Confirm both by readback — a write returning ok is not proof the EC took it.
        self._ec.write(REG_MODE, MODE_MANUAL)
        mode_ok = self._ec.read(REG_MODE) == MODE_MANUAL
        self._ec.write(REG_DUTY, duty)
        duty_ok = self._ec.read(REG_DUTY) == duty
        return mode_ok and duty_ok

    def _release(self) -> bool:
        # Hand the fan back to firmware by clearing the mode register. Confirm by
        # readback; retry so a transient failure self-heals. Auto mode is a clean
        # handback (no dead zone), so no fallback target is needed.
        for _ in range(_RELEASE_CONFIRM_RETRIES):
            self._ec.write(REG_MODE, MODE_AUTO)
            if self._ec.read(REG_MODE) == MODE_AUTO:
                return True
        return False

    def _read_rpm(self) -> Optional[int]:
        hi = self._ec.read(REG_RPM)
        lo = self._ec.read(REG_RPM + 1)
        if hi is None or lo is None:
            return None  # unreadable != a fake 0
        return (hi << 8) | lo

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        rpm = self._read_rpm()
        mode = self._ec.read(REG_MODE)
        # Ground truth from the mode register; fall back to our own drive state only
        # when the register is unreadable (ec_sys not loaded yet).
        if mode is not None:
            manual = mode == MODE_MANUAL
        else:
            manual = self._points is not None and self._drive_ok
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if manual else 2,
                          "rpm": rpm, "points": []}]}
