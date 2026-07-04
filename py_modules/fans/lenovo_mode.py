"""Coarse fan-mode backend for the Legion Go S (``VPC2004`` ideapad-style node).

The Go S firmware exposes NO writable temp→RPM curve: its ``fan1_target`` never
latches (always reads back 0) and it has no ``pwm*_auto_point*`` attributes. The
only working fan control is a coarse ``fan_mode`` node that selects a firmware
profile — the firmware then manages the actual RPM within each mode:

    0 = quiet        (~1375 rpm under load)
    1 = balanced     (~2000 rpm — the stock default)
    2 = performance  (~2715 rpm)

Values outside {0,1,2} are rejected by the firmware (the node reads back
unchanged), so ``set_mode`` verifies the write with a readback (never-fake).

This backend is ``mode_based``: it presents the existing NullFanBackend/
HwmonCurveBackend interface (``read_state``/``set_auto``/``restore_auto``/
``apply_curve_all``) so the rest of the plugin keeps working, but the UI hides the
freeform curve editor and offers the three modes instead. A freeform curve or the
adaptive learned curve can't be run here, so those paths honestly settle on the
default (balanced) mode rather than fabricating a curve.
"""

import glob
import os
from typing import Optional

from sysfs import read_int, write_str

# Stable, bounded device path — the fan_mode attribute hangs off the VPC2004 ACPI
# device. Globbed (not recursive) so a firmware revision that numbers the instance
# differently (VPC2004:01) still resolves, without ever walking /sys recursively
# (a documented QAM-freeze hazard).
_DEVICE_GLOB = "sys/bus/platform/devices/VPC2004:*"
_ATTR = "fan_mode"

# Valid coarse modes and their preset mapping.
_VALID_MODES = (0, 1, 2)
_DEFAULT_MODE = 1  # balanced — the stock firmware default (fail-safe target)
PRESET_TO_MODE: dict[str, int] = {"silent": 0, "balanced": 1, "performance": 2}


# sysfs read/write come from the shared py_modules/sysfs.py helpers (read_int /
# write_str) — no private copies here.


class LenovoFanModeBackend:
    """Legion Go S coarse fan-mode control via the ``VPC2004`` ``fan_mode`` node."""

    name: str = "lenovo_fan_mode"
    # Distinguishes this backend from the curve-based ones: the UI shows mode chips
    # (quiet/balanced/performance) instead of a draggable temp→pwm graph.
    mode_based: bool = True

    def __init__(self, root: str = "/") -> None:
        self._root = root
        self._path: Optional[str] = self._find_node()

    def _find_node(self) -> Optional[str]:
        for d in sorted(glob.glob(os.path.join(self._root, _DEVICE_GLOB))):
            candidate = os.path.join(d, _ATTR)
            if os.path.exists(candidate):
                return candidate
        return None

    @property
    def supported(self) -> bool:
        return self._path is not None

    # --- mode I/O ---------------------------------------------------------------

    def _current_mode(self) -> Optional[int]:
        return read_int(self._path) if self._path else None

    def _write_mode(self, mode: int) -> bool:
        """Raw write (no readback). Overridable in tests to simulate a stuck node."""
        return write_str(self._path, str(mode))

    def set_mode(self, mode: int) -> dict:
        """Write a coarse fan mode (0/1/2) and confirm via readback. Never raises."""
        if not self.supported:
            return {"ok": False, "detail": "fan_mode node not found"}
        try:
            mode = int(mode)
        except (TypeError, ValueError):
            return {"ok": False, "detail": f"invalid mode: {mode!r}"}
        if mode not in _VALID_MODES:
            return {"ok": False, "detail": f"mode out of range: {mode}"}
        if not self._write_mode(mode):
            return {"ok": False, "detail": "fan_mode write failed"}
        # never-fake: only report success if the node actually took the value.
        if self._current_mode() != mode:
            return {"ok": False, "detail": "fan_mode did not latch"}
        return {"ok": True, "detail": f"fan mode {mode} applied"}

    def apply_preset(self, preset_id: str) -> dict:
        """Apply a preset by mapping its id to a coarse mode. Custom/adaptive (not
        representable as a coarse mode) fall back to the default (balanced)."""
        return self.set_mode(PRESET_TO_MODE.get(preset_id, _DEFAULT_MODE))

    # --- shared backend interface ----------------------------------------------

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255,
                    "mode_based": True, "mode": None, "fans": []}
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "mode_based": True, "mode": self._current_mode(), "fans": []}

    def apply_curve_all(self, points: list) -> dict:
        """A canonical temp→pwm curve can't drive a coarse-mode fan. Settle on the
        default mode so the interface stays honest (never fabricate a curve)."""
        return self.set_mode(_DEFAULT_MODE)

    def set_curve(self, fan_key: str, points: list) -> dict:
        return self.apply_curve_all(points)

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        """No true firmware-auto exists; the stock default is balanced (mode 1)."""
        return self.set_mode(_DEFAULT_MODE)

    def restore_auto(self) -> dict:
        """Fail-safe on unload/uninstall: return the fan to the stock default mode."""
        return self.set_mode(_DEFAULT_MODE)
