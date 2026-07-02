import glob
import os

from sysfs import read_int, read_str

_SUPPLY = "sys/class/power_supply"


class BatteryReader:
    """Reads battery state + health from sysfs `power_supply`. World-readable, no
    root. Never raises; every optional field is None when the device doesn't
    expose it (honest 'unknown', never a fake zero).

    The battery dir is resolved once (re-resolved only if it vanishes), mirroring
    power/reader.py. AC-online is NOT read here — the RPC splices in the project's
    single source, lifecycle.read_on_ac.

    Energy is normalized to mWh: prefer energy_* (µWh); fall back to charge_*
    (µAh) × voltage_now (µV) for devices that only expose charge units."""

    def __init__(self, root="/"):
        self._root = root
        self._bat_dir = self._find_battery_dir()

    def _find_battery_dir(self):
        base = os.path.join(self._root, _SUPPLY)
        for d in sorted(glob.glob(os.path.join(base, "*"))):
            if read_str(os.path.join(d, "type")) == "Battery":
                return d
        return None

    def _dir(self):
        if self._bat_dir is None or not os.path.isdir(self._bat_dir):
            self._bat_dir = self._find_battery_dir()
        return self._bat_dir

    def _energy_mwh(self, d, energy_name, charge_name, voltage_uv):
        """mWh from energy_* (µWh) or charge_* (µAh) × voltage (µV)."""
        uwh = read_int(os.path.join(d, energy_name))
        if uwh is not None:
            return round(uwh / 1000)
        uah = read_int(os.path.join(d, charge_name))
        if uah is not None and voltage_uv:
            # µAh × µV = 1e-12 Wh → ×1e9 for mWh
            return round(uah * voltage_uv / 1_000_000_000)
        return None

    _ABSENT = {
        "present": False, "percent": None, "status": None, "health_percent": None,
        "cycle_count": None, "energy_now_mwh": None, "energy_full_mwh": None,
        "energy_full_design_mwh": None, "power_now_w": None, "eta_seconds": None,
    }

    def read(self):
        d = self._dir()
        if d is None:
            return dict(self._ABSENT)

        # For the µAh→mWh fallback, prefer the constant design voltage over the
        # live voltage_now so capacity/health don't jitter with load.
        voltage_uv = read_int(os.path.join(d, "voltage_min_design")) or read_int(
            os.path.join(d, "voltage_now")
        )
        now = self._energy_mwh(d, "energy_now", "charge_now", voltage_uv)
        full = self._energy_mwh(d, "energy_full", "charge_full", voltage_uv)
        design = self._energy_mwh(d, "energy_full_design", "charge_full_design", voltage_uv)

        # Cap at 100: a fresh battery can report full > design (health > 100%).
        health = min(100, round(full / design * 100)) if full and design else None

        # Power: prefer power_now (µW); fall back to current_now (µA) × voltage_now
        # (µV) for devices that only expose current (e.g. Steam Deck). 0 is a real
        # reading (idle) — only None means "unknown".
        power_uw = read_int(os.path.join(d, "power_now"))
        if power_uw is None:
            current_ua = read_int(os.path.join(d, "current_now"))
            voltage_now = read_int(os.path.join(d, "voltage_now"))
            if current_ua is not None and voltage_now:
                power_uw = round(current_ua * voltage_now / 1_000_000)
        power_w = round(power_uw / 1_000_000, 1) if power_uw is not None else None

        # cycle_count: many handhelds (ASUS Ally, Steam Deck, MSI Claw) expose the
        # node but the firmware never populates it, so it reads a literal 0. A used
        # battery with genuinely 0 cycles is implausible → treat 0 (and missing) as
        # unknown so the UI hides the chip rather than showing a fake "0 cycles".
        # Devices that report real counts (Legion) are unaffected.
        cycles = read_int(os.path.join(d, "cycle_count")) or None

        status = read_str(os.path.join(d, "status"))
        eta = None
        if status == "Discharging" and power_w and now:
            # mWh / W = h → ×3600 for seconds
            eta = round(now / power_w / 1000 * 3600)

        return {
            "present": True,
            "percent": read_int(os.path.join(d, "capacity")),
            "status": status,
            "health_percent": health,
            "cycle_count": cycles,
            "energy_now_mwh": now,
            "energy_full_mwh": full,
            "energy_full_design_mwh": design,
            "power_now_w": power_w,
            "eta_seconds": eta,
        }
