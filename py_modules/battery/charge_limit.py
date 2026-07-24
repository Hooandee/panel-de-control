import glob
import os

from sysfs import read_int, read_str, write_str

_SUPPLY = "sys/class/power_supply"
_HWMON = "sys/class/hwmon"
_THRESHOLD = "charge_control_end_threshold"
# The firmware accepts a wider range, but a floor of 20 keeps the UI sane (a
# 5% cap would be a footgun) and a ceiling of 100 = "no limit".
_MIN = 20
_MAX = 100


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class ChargeLimitBackend:
    """Interface + no-op default (= the unsupported case).

    `adjustable` = the threshold is a settable percentage (show a slider). False
    for fixed firmware caps that are only on/off (Lenovo conservation mode)."""

    supported = False
    adjustable = True
    # For fixed-cap (non-adjustable) backends, the percentage the firmware holds
    # when enabled — surfaced so the UI can state it explicitly. None = unknown.
    fixed_percent = None

    def get(self):
        return None

    def range(self):
        return (_MIN, _MAX)

    def set(self, percent):
        return False

    def disable(self):
        return False


class NullChargeLimit(ChargeLimitBackend):
    """No charge-limit interface on this device — honest 'not supported'."""


class _FileChargeLimit(ChargeLimitBackend):
    """A single sysfs file holding the cap percent. Subclasses locate the file and
    define the 'no limit' sentinel (`_OFF`) written on disable. Writing needs root
    (the plugin runs as root); every `set`/`disable` reads back to confirm the
    write stuck."""

    _OFF = _MAX

    def __init__(self, path):
        self._path = path
        self.supported = path is not None

    def get(self):
        if not self.supported:
            return None
        return read_int(self._path)

    def _write(self, value):
        if not self.supported:
            return False
        if not write_str(self._path, value):
            return False
        return self.get() == value

    def set(self, percent):
        return self._write(_clamp(int(percent), _MIN, _MAX))

    def disable(self):
        return self._write(self._OFF)


class SysfsChargeLimit(_FileChargeLimit):
    """Standard `charge_control_end_threshold` (ASUS/Lenovo and any kernel exposing
    it under power_supply/BAT*). 100 = no cap."""

    _OFF = _MAX

    def __init__(self, root="/"):
        super().__init__(self._find(root))

    @staticmethod
    def _find(root):
        base = os.path.join(root, _SUPPLY)
        for d in sorted(glob.glob(os.path.join(base, "*"))):
            p = os.path.join(d, _THRESHOLD)
            if os.path.exists(p):
                return p
        return None


class SteamDeckChargeLimit(_FileChargeLimit):
    """Steam Deck `steamdeck_hwmon/max_battery_charge_level`. 0 = no cap (distinct
    from the ASUS/Lenovo 100)."""

    _OFF = 0

    def __init__(self, root="/"):
        super().__init__(self._find(root))

    @staticmethod
    def _find(root):
        base = os.path.join(root, _HWMON)
        for h in sorted(glob.glob(os.path.join(base, "hwmon*"))):
            if read_str(os.path.join(h, "name")) == "steamdeck_hwmon":
                p = os.path.join(h, "max_battery_charge_level")
                if os.path.exists(p):
                    return p
        return None


class LenovoConservationMode(ChargeLimitBackend):
    """Lenovo (Legion Go) `conservation_mode`: a boolean (1=cap on) with a
    firmware-fixed threshold, NOT a settable percent.
    `adjustable=False` → the UI shows an on/off toggle (no slider) and states the
    fixed cap (`fixed_percent`, the Legion Go conservation level ≈80%)."""

    adjustable = False
    fixed_percent = 80

    def __init__(self, root="/"):
        self._path = self._find(root)
        self.supported = self._path is not None

    @staticmethod
    def _find(root):
        # NEVER recursive-glob /sys/devices — it walks the entire (huge) device
        # tree and blocks _init, hanging the UI on its spinner. Probe the stable
        # flat ACPI/platform symlinks first, then a bounded-depth fallback.
        patterns = [
            "sys/bus/platform/drivers/ideapad_acpi/VPC2004:*/conservation_mode",
            "sys/bus/acpi/devices/VPC2004:*/conservation_mode",
            "sys/bus/platform/devices/VPC2004:*/conservation_mode",
        ]
        for depth in range(2, 7):
            patterns.append(os.path.join("sys/devices", *(["*"] * depth), "conservation_mode"))
        for pat in patterns:
            matches = glob.glob(os.path.join(root, pat))
            if matches:
                return matches[0]
        return None

    def get(self):
        return None  # firmware-fixed threshold; percent unknown

    def set(self, percent):
        if not self.supported:
            return False
        return write_str(self._path, 1) and read_int(self._path) == 1

    def disable(self):
        if not self.supported:
            return False
        return write_str(self._path, 0) and read_int(self._path) == 0


def select_charge_limit(device, root="/"):
    """Pick the charge-limit strategy for the detected device (mirrors
    tdp.factory). Steam Deck uses its hwmon level; Legion falls back to Lenovo
    conservation mode (on/off) when the standard threshold is absent; ASUS uses
    the standard threshold. MSI Claw is probed via the standard path. Falls back
    to Null (honest) when nothing is present."""
    key = getattr(device, "key", "")
    if key.startswith("steam_deck"):
        candidates = [SteamDeckChargeLimit(root), SysfsChargeLimit(root)]
    elif key.startswith("legion"):
        candidates = [SysfsChargeLimit(root), LenovoConservationMode(root)]
    else:
        # Unrecognised / other: probe every known interface, standard threshold first.
        candidates = [SysfsChargeLimit(root), SteamDeckChargeLimit(root),
                      LenovoConservationMode(root)]
    for backend in candidates:
        if backend.supported:
            return backend
    return NullChargeLimit()
