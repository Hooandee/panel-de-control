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
_APEX_DUTY_FLOOR = 76
_RELEASE_CONFIRM_RETRIES = 3

_DMI_VENDOR = "ONE-NETBOOK"
_DMI_BOARD = "ONEXPLAYER APEX"
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
    experimental = True
    release_without_support = True
    min_rpm = 0
    max_rpm = 255  # the "target" IS the duty (0–255): base _duty_to_target is identity

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        self._ec = ec or EcSys(root=root)
        self._write_supported: Optional[bool] = None
        super().__init__(temp_fn=temp_fn, root=root)
        self._dmi_ok = self._dmi_matches()
        # The hwmon-vs-EC handoff can only flip on a kernel update (→ reboot → _init
        # re-runs), so probe once; supported is read on every monitor poll.
        self._hwmon_present = oxpec_hwmon_present(root)

    def _find_chip(self) -> Optional[str]:
        return None  # no hwmon node — support is DMI-based (see `supported`)

    @property
    def eligible(self) -> bool:
        return self._dmi_ok and not self._hwmon_present

    @property
    def supported(self) -> bool:
        return self.eligible and self._write_supported is True

    def _probe_supported(self) -> bool:
        self._write_supported = bool(self.eligible and self._ec.writable())
        return self._write_supported

    def _dmi_matches(self) -> bool:
        dmi = os.path.join(self._root, "sys/class/dmi/id")
        vendor = (_read(os.path.join(dmi, "board_vendor")) or "").upper()
        board = (_read(os.path.join(dmi, "board_name")) or "").upper()
        return vendor == _DMI_VENDOR and board == _DMI_BOARD

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        """Curve → a non-zero duty. A hot device forces full duty."""
        if self._points is None or temp is None:
            return None
        if temp >= _APEX_TEMP_GUARD_C:
            return 255
        return max(_APEX_DUTY_FLOOR, self._duty_to_target(_interp(self._points, temp)))

    def _apply_once_locked(self) -> bool:
        if self._points is not None:
            temp = self._temp_fn() if self._temp_fn else None
            if temp is None:
                self._drive_ok = False
                self._prev_target = None
                self._release()
                return False
        return super()._apply_once_locked()

    def _before_drive(self) -> bool:
        return self._probe_supported()

    def apply_curve_all(self, points: list) -> dict:
        self._probe_supported()
        return super().apply_curve_all(points)

    def _write_target(self, duty: int) -> bool:
        duty = max(_APEX_DUTY_FLOOR, min(255, int(duty)))
        # Land a non-zero duty before taking manual control.
        self._ec.write(REG_DUTY, duty)
        duty_ok = self._ec.read(REG_DUTY) == duty
        if not duty_ok:
            return False
        self._ec.write(REG_MODE, MODE_MANUAL)
        mode_ok = self._ec.read(REG_MODE) == MODE_MANUAL
        if not mode_ok:
            if not self._try_auto():
                self._force_full_manual()
            return False
        return True

    def _try_auto(self) -> bool:
        for _ in range(_RELEASE_CONFIRM_RETRIES):
            self._ec.write(REG_MODE, MODE_AUTO)
            if self._ec.read(REG_MODE) == MODE_AUTO:
                return True
        return False

    def _force_full_manual(self) -> bool:
        self._ec.write(REG_DUTY, 255)
        duty_ok = self._ec.read(REG_DUTY) == 255
        if not duty_ok:
            return False
        self._ec.write(REG_MODE, MODE_MANUAL)
        mode_ok = self._ec.read(REG_MODE) == MODE_MANUAL
        return mode_ok

    def _release(self) -> bool:
        # Hand the fan back to firmware by clearing the mode register. Confirm by
        # readback; retry so a transient failure self-heals.
        if self._try_auto():
            return True
        self._force_full_manual()
        return False

    def _read_rpm(self) -> Optional[int]:
        hi = self._ec.read(REG_RPM)
        lo = self._ec.read(REG_RPM + 1)
        if hi is None or lo is None:
            return None  # unreadable != a fake 0
        return (hi << 8) | lo

    def read_state(self) -> dict:
        if not self._probe_supported():
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
