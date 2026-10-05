"""Last-resort fan-curve backend for hwmon chips that expose the standard manual
PWM interface (``pwmN`` + ``pwmN_enable``) without a vendor curve-table. Reuses the
software-loop scaffolding: read the driving temp, interpolate the canonical 0-255
curve and write ``pwmN`` directly (``pwmN_enable`` = 1 manual). Release hands each
fan back to firmware auto.

Only engaged when a chip also exposes a real ``fanN_input`` tach, so we never drive
an unrelated PWM. Graphics-driver chips are skipped: a discrete GPU's firmware owns
its fan, and driving it from the system curve starves the card under load. The
hottest curve point stays above the safety floor, and a missing temp reading
releases to auto rather than holding a stale duty.
"""

import glob
import os
import re

from fans.control import _interp, _read, _read_int, _write, _SAFE_MAX_TEMP_FLOOR
from fans.software_loop import _HWMON, SoftwareLoopBackend

_THERMAL = "sys/class/thermal"
PWM_FAN_CHIP = "pwmfan"
PWM_FAN_COOLING = "pwm-fan"
FAILSAFE_DUTY = 128
AUTO_PRESET = "balanced"

_ENABLE_MANUAL = 1
_ENABLE_AUTO = 2
GPU_DRIVER_CHIPS = frozenset({"amdgpu", "radeon", "nouveau", "i915", "xe"})


class GenericPwmFanBackend(SoftwareLoopBackend):
    name = "generic-pwm"

    def __init__(self, temp_fn=None, root: str = "/", min_duty: int = 0,
                 spinning_only: bool = False) -> None:
        self._orig_enable: dict[int, int] = {}
        self._fans: list[int] = []
        self._min_duty = max(0, min(255, int(min_duty)))
        # Desktop boards expose every header, connected or not; an idle tach at 0
        # can be an empty header or a semi-passive fan, and neither is taken.
        self._spinning_only = spinning_only
        super().__init__(temp_fn=temp_fn, root=root)
        self.firmware_auto = self._has_firmware_auto()

    def _has_firmware_auto(self) -> bool:
        # pwm-fan has no automatic mode: only a thermal zone bound to its cooling device moves it.
        if self._dir is None or _read(os.path.join(self._dir, "name")) != PWM_FAN_CHIP:
            return True
        return pwm_fan_thermally_bound(self._root)

    def set_auto(self, fan_key=None) -> dict:
        if self.firmware_auto or not self.supported:
            return super().set_auto(fan_key)
        from fans.presets import RESOLVED
        result = self.apply_curve_all([list(point) for point in RESOLVED[AUTO_PRESET]])
        return {"ok": result["ok"], "detail": "panel automatic curve (no firmware automatic mode)"}

    def restore_auto(self) -> dict:
        if self.firmware_auto or not self.supported:
            return super().restore_auto()
        self.stop()
        with self._io_lock:
            self._points = None
            self._drive_ok = False
            self._prev_target = None
            ok = True
            for m in self._fans:
                manual = (_write(self._enable(m), str(_ENABLE_MANUAL))
                          and _read_int(self._enable(m)) == _ENABLE_MANUAL)
                ok = manual and _write(self._pwm(m), str(FAILSAFE_DUTY)) and ok
        return {"ok": ok, "detail": f"left at fail-safe duty {FAILSAFE_DUTY} (no firmware automatic mode)"}

    def _find_chip(self):
        for d in sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*"))):
            if _read(os.path.join(d, "name")) in GPU_DRIVER_CHIPS:
                continue
            fans = []
            for enable_path in sorted(glob.glob(os.path.join(d, "pwm[0-9]*_enable"))):
                m = re.search(r"pwm(\d+)_enable$", enable_path)
                if not m:
                    continue
                idx = m.group(1)
                # Require a same-index tach so we only drive a pwm backed by a real fan.
                if not all(os.path.exists(os.path.join(d, name))
                           for name in (f"pwm{idx}", f"fan{idx}_input")):
                    continue
                if self._spinning_only and not (_read_int(
                        os.path.join(d, f"fan{idx}_input")) or 0) > 0:
                    continue
                fans.append(int(idx))
            if fans:
                self._fans = fans
                return d
        return None

    def _pwm(self, m: int) -> str:
        return os.path.join(self._dir, f"pwm{m}")

    def _enable(self, m: int) -> str:
        return os.path.join(self._dir, f"pwm{m}_enable")

    def _before_drive(self) -> bool:
        for m in self._fans:
            prior = _read_int(self._enable(m))
            # Release must hand back to a real auto mode, never to our own manual (1).
            self._orig_enable.setdefault(
                m, prior if prior not in (None, _ENABLE_MANUAL) else _ENABLE_AUTO)
        return True

    def _apply_once_locked(self) -> bool:
        """Write the interpolated pwm to every fan (caller holds `_io_lock`). Engage
        manual mode (`pwmN_enable` = 1) and confirm it by readback BEFORE writing the
        duty: `pwmN` only takes effect in manual mode and some drivers (gpd_fan) reject
        a `pwmN` write with -EPERM while still in auto. If manual engages but the duty
        write is refused, hand that fan back to firmware auto rather than leave it stuck
        in manual at a stale/max duty. Returns True only when every fan landed (manual
        readback AND duty write, never a write alone). No temp → release."""
        if self._points is None:
            self._drive_ok = False
            return False
        temp = self._temp_fn() if self._temp_fn else None
        if temp is None:
            self._release()  # no safe reading → hand back rather than hold a stale duty
            self._drive_ok = False
            return False
        pwm = _interp(self._points, temp)
        if temp >= self._points[-1][0]:
            pwm = max(pwm, _SAFE_MAX_TEMP_FLOOR)  # never idle at/above the hottest point
        pwm = max(self._min_duty, min(255, pwm))
        all_ok = True
        for m in self._fans:
            manual = (_write(self._enable(m), str(_ENABLE_MANUAL))
                      and _read_int(self._enable(m)) == _ENABLE_MANUAL)
            pwm_ok = _write(self._pwm(m), str(pwm)) if manual else False
            if not (manual and pwm_ok):
                # Couldn't take manual control or the duty was refused → return this
                # fan to its firmware auto mode (never leave it stuck manual@max).
                _write(self._enable(m), str(self._orig_enable.get(m, _ENABLE_AUTO)))
                all_ok = False
        self._drive_ok = all_ok
        return all_ok

    def _release(self) -> bool:
        ok = True
        for m in self._fans:
            ok = _write(self._enable(m), str(self._orig_enable.get(m, _ENABLE_AUTO))) and ok
        return ok

    def _fan_enable(self, m: int) -> int:
        """Manual(1) iff the hardware is ACTUALLY in manual mode (enable node read
        back) — never our write alone (it can be refused), and never a tachometer
        reading (a spin can be the firmware's, and 0 rpm can't tell spin-up/dead from
        ignored). The readback is the actual control state."""
        return _ENABLE_MANUAL if _read_int(self._enable(m)) == _ENABLE_MANUAL else _ENABLE_AUTO

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        fans = []
        for m in self._fans:
            rpm = _read_int(os.path.join(self._dir, f"fan{m}_input"))
            fans.append({"key": f"fan{m}", "enable": self._fan_enable(m),
                         "rpm": rpm, "points": []})
        return {"supported": True, "source": self.name, "pwm_max": 255, "fans": fans,
                "firmware_auto": self.firmware_auto}


def pwm_fan_thermally_bound(root: str = "/") -> bool:
    devices = set()
    for device in glob.glob(os.path.join(root, _THERMAL, "cooling_device*")):
        if _read(os.path.join(device, "type")) == PWM_FAN_COOLING:
            devices.add(os.path.basename(device))
    if not devices:
        return False
    for link in glob.glob(os.path.join(root, _THERMAL, "thermal_zone*", "cdev[0-9]*")):
        try:
            if os.path.basename(os.readlink(link)) in devices:
                return True
        except OSError:
            continue
    return False
