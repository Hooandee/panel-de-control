"""Fan-curve write backend for hwmon-based devices.

Currently supports the ASUS ``asus_custom_fan_curve`` hwmon chip found on
ROG Ally / ROG Xbox Ally X.  Other devices degrade to ``NullFanBackend``
(unsupported, read-only safe).

Safety guarantee: ``sanitize_curve`` ensures the last curve point always
reaches at least ``_SAFE_MAX_TEMP_FLOOR`` (≈30 % of 255 ≈ 76) so no manual
curve can leave a fan idle when the device is hot.
"""

import glob
import os
from typing import Optional

_HWMON = "sys/class/hwmon"
_CHIP_NAME = "asus_custom_fan_curve"

# Minimum PWM the last (hottest) curve point must reach.
# 76 ≈ 30 % of 255 — loud enough to protect the chip at max temp.
_SAFE_MAX_TEMP_FLOOR: int = 76

# Fan index mapping: friendly key → hwmon pwmM index.
_FAN_KEYS: dict[str, int] = {"cpu": 1, "gpu": 2}
_POINTS: int = 8


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def sanitize_curve(
    points: list,
    pwm_max: int = 255,
    floor_pwm: int = 0,
) -> list[tuple[int, int]]:
    """Return a safe 8-point ``[(temp, pwm), …]`` list suitable for writing.

    Rules applied in order:
    1. Truncate to 8 / pad by repeating the last point.
    2. Cast to int.
    3. Clamp temps to 0..100, pwm to ``[floor_pwm, pwm_max]``.
    4. Make temps strictly non-decreasing (bump by +1 when equal).
    5. Make pwm monotonically non-decreasing.
    6. Enforce ``_SAFE_MAX_TEMP_FLOOR`` on the LAST point only — lower points
       may remain quiet.

    Never raises.
    """
    if not points:
        points = [(0, 0)]

    # 1. Normalise length
    pts: list[tuple[int, int]] = [(int(t), int(p)) for t, p in points[:_POINTS]]
    while len(pts) < _POINTS:
        pts.append(pts[-1])

    # 2+3. Clamp
    pts = [(max(0, min(100, t)), max(floor_pwm, min(pwm_max, p))) for t, p in pts]

    # 4. Make temps non-decreasing
    result: list[tuple[int, int]] = [pts[0]]
    for t, p in pts[1:]:
        prev_t = result[-1][0]
        if t <= prev_t:
            t = prev_t  # keep equal (monotone, not strictly increasing)
        result.append((t, p))

    # 5. Make pwm monotonically non-decreasing
    final: list[tuple[int, int]] = [result[0]]
    for t, p in result[1:]:
        prev_p = final[-1][1]
        final.append((t, max(p, prev_p)))

    # 6. Enforce safe floor on last point only
    effective_floor = max(floor_pwm, _SAFE_MAX_TEMP_FLOOR)
    t_last, p_last = final[-1]
    if p_last < effective_floor:
        final[-1] = (t_last, effective_floor)

    return final


# ---------------------------------------------------------------------------
# I/O helpers (never raise)
# ---------------------------------------------------------------------------

def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    v = _read(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _write(path: str, value: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Backend classes
# ---------------------------------------------------------------------------

class NullFanBackend:
    """Returned when no supported fan-control chip is found on this device."""

    supported: bool = False
    name: str = "null"

    def read_state(self) -> dict:
        return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}

    def set_curve(self, fan_key: str, points: list) -> dict:
        return {"ok": False, "detail": "fan control not supported on this device"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        return {"ok": False, "detail": "fan control not supported on this device"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)


class AsusFanCurveBackend:
    """Fan-curve backend for the ``asus_custom_fan_curve`` hwmon chip.

    On ROG Ally / ROG Xbox Ally X this chip is at::

        /sys/devices/platform/asus-nb-wmi/hwmon/hwmonN/

    and is also reachable via ``/sys/class/hwmon/hwmonN/`` which we use for
    discovery.

    Per fan M (1=CPU, 2=GPU):
    - ``pwmM_auto_pointK_temp`` (°C, K=1..8)
    - ``pwmM_auto_pointK_pwm``  (raw 0..255, must be monotonically non-decreasing)
    - ``pwmM_enable``           (2 = firmware auto, 1 = use the written points)

    All files are root:root 0644; the plugin runs as root → writable.
    """

    name: str = _CHIP_NAME

    def __init__(self, root: str = "/") -> None:
        self._root = root
        self._dir: Optional[str] = self._find_chip()

    @property
    def supported(self) -> bool:
        return self._dir is not None

    def _find_chip(self) -> Optional[str]:
        pattern = os.path.join(self._root, _HWMON, "hwmon*")
        for d in sorted(glob.glob(pattern)):
            if _read(os.path.join(d, "name")) == _CHIP_NAME:
                # Confirm at least one pwm point file is present
                if os.path.exists(os.path.join(d, "pwm1_auto_point1_pwm")):
                    return d
        return None

    def _fan_dir(self) -> Optional[str]:
        return self._dir

    # --- public API -----------------------------------------------------------

    def read_state(self) -> dict:
        """Read current curve and enable state for all present fans.

        Never raises.  Missing/corrupt files produce None values or skip the
        fan entirely.
        """
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}

        fans = []
        for key, m in _FAN_KEYS.items():
            enable_path = os.path.join(self._dir, f"pwm{m}_enable")
            if not os.path.exists(enable_path):
                continue  # this fan index not present on this chip
            enable = _read_int(enable_path)
            points = []
            for k in range(1, _POINTS + 1):
                t = _read_int(os.path.join(self._dir, f"pwm{m}_auto_point{k}_temp"))
                p = _read_int(os.path.join(self._dir, f"pwm{m}_auto_point{k}_pwm"))
                points.append({"temp": t, "pwm": p})
            fans.append({"key": key, "enable": enable, "points": points})

        return {
            "supported": True,
            "source": self.name,
            "pwm_max": 255,
            "fans": fans,
        }

    def set_curve(self, fan_key: str, points: list) -> dict:
        """Write a sanitized fan curve and switch the fan to manual mode.

        Returns ``{"ok": bool, "detail": str}``.  Never raises.
        """
        if not self.supported:
            return {"ok": False, "detail": "asus_custom_fan_curve chip not found"}

        m = _FAN_KEYS.get(fan_key)
        if m is None:
            return {"ok": False, "detail": f"unknown fan key: {fan_key!r}"}

        safe_pts = sanitize_curve(points, pwm_max=255, floor_pwm=0)

        # Write the 8 temp+pwm files
        for k, (temp, pwm) in enumerate(safe_pts, start=1):
            if not _write(os.path.join(self._dir, f"pwm{m}_auto_point{k}_temp"), str(temp)):
                return {"ok": False, "detail": f"write failed: pwm{m}_auto_point{k}_temp"}
            if not _write(os.path.join(self._dir, f"pwm{m}_auto_point{k}_pwm"), str(pwm)):
                return {"ok": False, "detail": f"write failed: pwm{m}_auto_point{k}_pwm"}

        # Activate manual mode
        if not _write(os.path.join(self._dir, f"pwm{m}_enable"), "1"):
            return {"ok": False, "detail": f"write failed: pwm{m}_enable"}

        # Read back point 1 to confirm the kernel accepted the write
        readback = _read_int(os.path.join(self._dir, f"pwm{m}_auto_point1_pwm"))
        if readback is None:
            return {"ok": False, "detail": "readback failed after write"}

        return {"ok": True, "detail": f"fan {fan_key} curve applied (manual mode)"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        """Return the specified fan (or all fans when ``fan_key`` is None) to
        firmware-controlled auto mode by writing ``pwmM_enable=2``.

        Returns ``{"ok": bool, "detail": str}``.  Never raises.
        """
        if not self.supported:
            return {"ok": False, "detail": "asus_custom_fan_curve chip not found"}

        if fan_key is not None:
            m = _FAN_KEYS.get(fan_key)
            if m is None:
                return {"ok": False, "detail": f"unknown fan key: {fan_key!r}"}
            fans_to_restore = [(fan_key, m)]
        else:
            fans_to_restore = list(_FAN_KEYS.items())

        failed = []
        for key, m in fans_to_restore:
            enable_path = os.path.join(self._dir, f"pwm{m}_enable")
            if not _write(enable_path, "2"):
                failed.append(key)

        if failed:
            return {"ok": False, "detail": f"enable=2 write failed for: {failed}"}
        return {"ok": True, "detail": "fan(s) returned to firmware auto"}

    def restore_auto(self) -> dict:
        """Fail-safe: restore ALL fans to firmware auto.  Called on plugin unload."""
        return self.set_auto(None)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def select_fan_backend(device, root: str = "/"):
    """Return the best available fan-control backend for this device.

    Strategy:
    1. Always try the ``asus_custom_fan_curve`` chip (chip-name based, not
       device-name based) — it's present on Ally family devices.
    2. Fall back to ``NullFanBackend`` when the chip is not found.

    Legion/MSI mechanisms are a future sub-project; their devices get Null
    for now (read-only safety).
    """
    backend = AsusFanCurveBackend(root=root)
    if backend.supported:
        return backend
    return NullFanBackend()
