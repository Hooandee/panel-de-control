"""Last-resort fan-curve backend for hwmon chips that expose the standard manual
PWM interface (``pwmN`` + ``pwmN_enable``) without a vendor curve-table. Reuses the
software-loop scaffolding: read the driving temp, interpolate the canonical 0-255
curve and write ``pwmN`` directly (``pwmN_enable`` = 1 manual). Release hands each
fan back to firmware auto.

Only engaged when a chip also exposes a real ``fanN_input`` tach, so we never drive
an unrelated PWM. The hottest curve point stays above the safety floor, and a missing
temp reading releases to auto rather than holding a stale duty.
"""

import glob
import os
import re

from fans.control import _interp, _read_int, _write, _SAFE_MAX_TEMP_FLOOR
from fans.software_loop import _HWMON, SoftwareLoopBackend

_ENABLE_MANUAL = 1
_ENABLE_AUTO = 2


class GenericPwmFanBackend(SoftwareLoopBackend):
    name = "generic-pwm"

    def __init__(self, temp_fn=None, root: str = "/") -> None:
        self._orig_enable: dict[int, int] = {}
        self._fans: list[int] = []
        super().__init__(temp_fn=temp_fn, root=root)

    def _find_chip(self):
        for d in sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*"))):
            fans = []
            for enable_path in sorted(glob.glob(os.path.join(d, "pwm[0-9]*_enable"))):
                m = re.search(r"pwm(\d+)_enable$", enable_path)
                if not m:
                    continue
                idx = m.group(1)
                # Require a same-index tach so we only drive a pwm backed by a real fan.
                if all(os.path.exists(os.path.join(d, name))
                       for name in (f"pwm{idx}", f"fan{idx}_input")):
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

    def _apply_once(self) -> None:
        if self._points is None:
            return
        temp = self._temp_fn() if self._temp_fn else None
        if temp is None:
            self._release()  # no safe reading → hand back rather than hold a stale duty
            return
        pwm = _interp(self._points, temp)
        if temp >= self._points[-1][0]:
            pwm = max(pwm, _SAFE_MAX_TEMP_FLOOR)  # never idle at/above the hottest point
        pwm = max(0, min(255, pwm))
        for m in self._fans:
            _write(self._enable(m), str(_ENABLE_MANUAL))
            _write(self._pwm(m), str(pwm))

    def _release(self) -> bool:
        ok = True
        for m in self._fans:
            ok = _write(self._enable(m), str(self._orig_enable.get(m, _ENABLE_AUTO))) and ok
        return ok

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        fans = [{"key": f"fan{m}", "enable": _read_int(self._enable(m)),
                 "rpm": _read_int(os.path.join(self._dir, f"fan{m}_input")),
                 "points": []} for m in self._fans]
        return {"supported": True, "source": self.name, "pwm_max": 255, "fans": fans}
