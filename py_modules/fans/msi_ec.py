"""MSI Claw 8 AI+ fan backend — EC register 0x33 step control via ec_sys debugfs.

The msi_wmi_platform driver is read-only on the Claw's kernel (no writable pwm),
so the hwmon curve backend degrades to unsupported. Control is instead done over
the Embedded Controller: register ``0x33`` selects the fan speed, encoded as

    low nibble  = 0    -> MANUAL (our level takes effect)
    high nibble = 0..e -> discrete speed level (both fans move together)
    byte 0x05          -> AUTO / firmware (low nibble != 0 hands control back)

Level table (high nibble -> approx RPM): 0x0≈2500, 0x4≈3690, 0x8≈4615, 0xc≈5450,
0xe≈5850 (top). We map the canonical 0–255 pwm curve to the nearest of these
discrete levels, mirroring how the Legion loop maps pwm→RPM. Failsafe = write 0x05
(firmware auto).

Readback: RPM at 0xc9/0xcb (``RPM = 480000 / value``); a write is only reported
successful when the register access succeeds. Writes go through ec_sys debugfs
(``/sys/kernel/debug/ec/ec0/io``) loaded with ``write_support=1``.

SAFETY: reuses the software-loop re-assert cadence + the shared hot-point safety
floor (``sanitize_curve``). Above the safe temperature the driven level is never
low; any read/write failure and every unload/release path writes 0x05 so the fan
returns to firmware control rather than being left slow.
"""

from typing import Callable, Optional

from fans.control import _interp, _is_msi_vendor
from fans.ec_io import EcSys as _EcSys
from fans.software_loop import SoftwareLoopBackend

# EC register map.
REG_FAN = 0x33     # write: low nibble 0 = manual, high nibble = level; 0x05 = auto
REG_RPM_A = 0xC9   # readback: RPM = 480000 / value
REG_RPM_B = 0xCB   # second fan (same lock-step APU)

# Release-to-firmware sentinel. Any value whose low nibble != 0 hands the fan back
# to the firmware; 0x05 is the firmware's default auto value.
EC_AUTO = 0x05

# Usable manual bytes (low nibble 0). High nibble → approx RPM across the range:
# 0x00≈2500, 0x40≈3690, 0x80≈4615, 0xc0≈5450, 0xe0≈5850(max).
EC_LEVELS = (0x00, 0x40, 0x80, 0xC0, 0xE0)

# Thermal-safety backstop for the discrete backend: at or above this temperature
# the driven byte is clamped up to _SAFE_MIN_HOT_BYTE regardless of the curve.
# sanitize_curve only floors the hottest curve *point*'s pwm, which discretizes to
# a low level (pwm 76 → 0x40) and can leave a quiet curve on a slow step while the
# APU is already hot, so we enforce a real temperature threshold here in °C. 73 °C
# sits below the firmware's own hot anchors while still leaving throttle headroom.
_SAFE_HOT_TEMP_C = 73
_SAFE_MIN_HOT_BYTE = 0xC0  # ≈5450 rpm — the minimum driven level once hot

_RPM_CONST = 480000


def pwm_to_ec_byte(pwm: int) -> int:
    """Map a canonical pwm (0..255) to the nearest discrete EC manual byte.

    Result is always one of ``EC_LEVELS`` with the low nibble 0 (manual). Pure;
    monotonic non-decreasing in pwm.
    """
    p = max(0, min(255, int(pwm)))
    n = len(EC_LEVELS)
    idx = int(round(p / 255 * (n - 1)))
    return EC_LEVELS[max(0, min(n - 1, idx))]


class MsiEcFanBackend(SoftwareLoopBackend):
    """MSI Claw: write a discrete speed level to EC 0x33; release = 0x05.

    Discrete-step control, so the base loop's continuous duty→RPM mapping is
    overridden — the "target" IS the EC byte. The re-assert loop, ownership, and
    failsafe all come from SoftwareLoopBackend.
    """

    name = "msi-claw-ec"

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        self._ec = ec if ec is not None else _EcSys(root=root)
        super().__init__(temp_fn=temp_fn, root=root)
        self._is_msi = _is_msi_vendor(root)

    def _find_chip(self) -> Optional[str]:
        return None  # EC-based, not hwmon; `supported` is capability-based instead

    @property
    def supported(self) -> bool:
        # MSI vendor AND the EC io file is actually writable. Never claims control
        # on a kernel that only exposes ec_sys read-only.
        return self._is_msi and self._ec.writable()

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        """Return the EC byte to drive at *temp*, or None if no curve is set.

        Overrides the base RPM mapping: the target is a discrete manual byte. Above
        _SAFE_HOT_TEMP_C the driven byte is clamped up to _SAFE_MIN_HOT_BYTE so a
        quiet curve can never sit on a slow step while the APU is hot.
        """
        if self._points is None or temp is None:
            return None
        byte = pwm_to_ec_byte(_interp(self._points, temp))
        if temp >= _SAFE_HOT_TEMP_C:
            byte = max(byte, _SAFE_MIN_HOT_BYTE)
        return byte

    def _write_target(self, byte: int) -> bool:
        return self._ec.write(REG_FAN, byte)

    def _release(self) -> bool:
        return self._ec.write(REG_FAN, EC_AUTO)

    def _read_rpm(self) -> Optional[int]:
        val = self._ec.read(REG_RPM_A)
        if not val:  # None (read failed) or 0 (no reading) → honest unknown
            return None
        return _RPM_CONST // val
