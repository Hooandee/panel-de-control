import glob
import os
import time

from sysfs import read_str
from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult

_FW_BASE = "sys/class/firmware-attributes"
_PP_BASE = "sys/class/platform-profile"
# ASUS exposes a SECOND, legacy PL1 interface (asus-nb-wmi: direct ppt files) that Steam
# and HHD also write. The effective SoC limit is the last write across BOTH interfaces,
# so a write mirrors our (clamped) setpoint here too to stay authoritative under a game.
_LEGACY_BASE = "sys/devices/platform/asus-nb-wmi"
_LEGACY_NODES = (("pl1", "ppt_pl1_spl"), ("pl2", "ppt_pl2_sppt"), ("pl3", "ppt_fppt"))
_RAIL_ATTRS = (
    ("pl1", "ppt_pl1_spl"),
    ("pl2", "ppt_pl2_sppt"),
    ("pl3", "ppt_pl3_fppt"),
)

# Boost headroom derived from sustained PL1 when the user sets a single TDP value.
# PL2 (slow) and PL3 (fast) are scaled above PL1, then clamped to each rail's sysfs max.
_PL2_BOOST_RATIO = 1.2
_PL3_BOOST_RATIO = 1.4


def _normalise_rail_floors(values):
    if not isinstance(values, dict):
        return {}
    known_rails = {rail for rail, _attr in _RAIL_ATTRS}
    floors = {}
    for rail, value in values.items():
        if rail not in known_rails:
            continue
        try:
            floor = int(value)
        except (TypeError, ValueError):
            continue
        if floor > 0:
            floors[rail] = floor
    return floors


def _normalise_rail_values(values):
    if not isinstance(values, dict):
        return {}
    known_rails = {rail for rail, _attr in _RAIL_ATTRS}
    normalised = {}
    for rail, value in values.items():
        if rail not in known_rails:
            continue
        try:
            normalised[rail] = int(value)
        except (TypeError, ValueError):
            continue
    return normalised


class FirmwareAttrBackend(TDPBackend):
    """TDP via kernel firmware-attributes. Covers ASUS (asus-armoury), Lenovo
    (lenovo-wmi-other), MSI (msi-wmi-platform): ppt_pl1_spl/ppt_pl2_sppt/ppt_pl3_fppt
    with current_value (watts) + min_value/max_value. Never raises."""

    def __init__(
        self,
        driver_prefix,
        fallback,
        root="/",
        profile_name=None,
        is_generic=False,
        rail_floors=None,
        ignored_live_maxes=None,
        cap_boost_to_active=False,
        readback_settle_delays=None,
    ):
        self.name = f"firmware-attr:{driver_prefix}"
        self._fallback = fallback
        self._root = root
        self._profile_name = profile_name  # Lenovo: set this platform-profile to "custom" first
        self._is_generic = is_generic
        self._rail_floors = _normalise_rail_floors(rail_floors)
        self._ignored_live_maxes = _normalise_rail_values(ignored_live_maxes)
        self.cap_boost_to_active = bool(cap_boost_to_active)
        self._readback_settle_delays = tuple(
            float(delay) for delay in (readback_settle_delays or ())
        )
        self._dir = self._find_driver_dir(driver_prefix)
        self.supported = self._dir is not None and os.path.exists(self._attr("ppt_pl1_spl"))
        self._pp_dir = self._find_profile_dir()  # static, resolved once
        self._pp_choices = None                  # parsed lazily, then cached
        self._legacy = self._find_legacy_nodes(driver_prefix)  # ASUS dual-interface
        self._rails = tuple(
            rail
            for rail, attr in _RAIL_ATTRS
            if os.path.exists(self._attr(attr)) or rail in self._legacy
        )
        self.supports_levels = any(rail != "pl1" for rail in self._rails)

    def _live_bounds(self, attr):
        # Read live, never cache: the firmware ceiling is dynamic.
        lo = self._read_int(self._attr(attr, "min_value"))
        hi = self._read_int(self._attr(attr, "max_value"))
        return lo, hi

    def _find_legacy_nodes(self, driver_prefix):
        """Detect the legacy asus-nb-wmi ppt files (the second PL1 interface). ASUS only;
        empty on other vendors and on kernels that dropped the legacy nodes."""
        if not driver_prefix.startswith("asus"):
            return {}
        base = os.path.join(self._root, _LEGACY_BASE)
        return {rail: os.path.join(base, node)
                for rail, node in _LEGACY_NODES
                if os.path.exists(os.path.join(base, node))}

    def _write_legacy(self, targets):
        failed = []
        for rail in ("pl3", "pl2", "pl1"):
            path = self._legacy.get(rail)
            if path and rail in targets and not self._write(path, targets[rail]):
                failed.append(f"asus-nb-wmi/{rail}")
        return failed

    def reconciliation_levels(self, levels):
        return {
            rail: int(levels[rail])
            for rail in self._rails
            if rail in levels
        }

    def _find_driver_dir(self, prefix):
        base = os.path.join(self._root, _FW_BASE)
        for d in sorted(glob.glob(os.path.join(base, prefix + "*"))):
            if os.path.isdir(os.path.join(d, "attributes")):
                return d
        return None

    def _attr(self, name, leaf="current_value"):
        return os.path.join(self._dir or "", "attributes", name, leaf)

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _write(self, path, value):
        try:
            with open(path, "w") as f:
                f.write(f"{value}\n")
            return True
        except OSError:
            return False

    def get_limits(self):
        if not self.supported:
            return self._fallback
        if not self._is_generic:
            # The profile is the authority for the range; the firmware's reported max
            # lies (and, cached, stranded users at 15 W). Writes still clamp live.
            return self._fallback
        mn, mx = self._live_bounds("ppt_pl1_spl")
        max_ac_w = min(
            self._fallback.max_ac_w,
            mx if mx is not None else self._fallback.max_ac_w,
        )
        max_w = min(self._fallback.max_w, max_ac_w)
        live_min = mn if mn is not None else self._fallback.min_w
        min_w = min(max_w, max(self._fallback.min_w, live_min))
        default_w = max(min_w, min(self._fallback.default_w, max_w))
        return TdpLimits(
            min_w=min_w,
            default_w=default_w,
            max_w=max_w,
            max_ac_w=max_ac_w,
        )

    def _find_profile_dir(self):
        if not self._profile_name:
            return None
        base = os.path.join(self._root, _PP_BASE)
        for d in sorted(glob.glob(os.path.join(base, "*"))):
            if read_str(os.path.join(d, "name")) == self._profile_name:
                return d
        return None

    def _set_custom_profile(self):
        if self._pp_dir:
            self._write(os.path.join(self._pp_dir, "profile"), "custom")

    def read_profile(self):
        """Active firmware profile (e.g. 'performance', 'custom'), or None. Read live —
        the active profile changes when the user picks a mode."""
        return read_str(os.path.join(self._pp_dir, "profile")) if self._pp_dir else None

    def profile_choices(self):
        """Available firmware profiles, e.g. ['low-power','balanced','performance',
        'custom']. Static, cached. Empty when unsupported."""
        if self._pp_choices is None:
            raw = read_str(os.path.join(self._pp_dir, "choices")) if self._pp_dir else None
            self._pp_choices = raw.split() if raw else []
        return self._pp_choices

    def set_profile(self, mode):
        """Write a named firmware profile. Returns True on confirmed readback; False
        for an unknown mode or when unsupported."""
        if not self._pp_dir or mode not in self.profile_choices():
            return False
        self._write(os.path.join(self._pp_dir, "profile"), mode)
        return self.read_profile() == mode

    def level_limits(self):
        if self._is_generic:
            out = {}
            for key, attr in _RAIL_ATTRS:
                if key not in self._rails:
                    continue
                mn, mx = self._live_bounds(attr)
                if mn is not None and mx is not None:
                    hi = min(mx, self._profile_rail_max(attr))
                    lo = min(
                        hi,
                        max(
                            self._fallback.min_w,
                            mn,
                            self._rail_floors.get(key, self._fallback.min_w),
                        ),
                    )
                    out[key] = {"min": lo, "max": hi}
            return out
        mn = self._fallback.min_w
        bounds = {
            rail: {"min": mn, "max": self._profile_rail_max(attr)}
            for rail, attr in _RAIL_ATTRS
        }
        for rail, floor in self._rail_floors.items():
            bound = bounds[rail]
            bound["min"] = min(bound["max"], max(bound["min"], floor))
        return {rail: bounds[rail] for rail in self._rails}

    def _profile_rail_max(self, attr):
        """Recognised-device write ceiling for a rail, mirroring level_limits(): PL1 =
        charger max, boost rails profile-scaled. The profile is the authority — not the
        firmware's reported max, which some ASUS kernels report as a bogus 150 W."""
        mx = self._fallback.max_ac_w
        if self.cap_boost_to_active:
            return mx
        if attr == "ppt_pl2_sppt":
            return round(mx * _PL2_BOOST_RATIO)
        if attr == "ppt_pl3_fppt":
            return round(mx * _PL3_BOOST_RATIO)
        return mx

    def _effective_live_max(self, rail, reported):
        if reported == self._ignored_live_maxes.get(rail):
            return None
        return reported

    def _clamp_live(self, value, attr):
        mn, mx = self._live_bounds(attr)
        safe_hi = self._profile_rail_max(attr)
        rail = next(
            (rail for rail, rail_attr in _RAIL_ATTRS if rail_attr == attr),
            None,
        )
        live_hi = self._effective_live_max(rail, mx)
        hi = min(live_hi if live_hi is not None else safe_hi, safe_hi)
        live_lo = mn if mn is not None else self._fallback.min_w
        floor = self._rail_floors.get(rail, self._fallback.min_w)
        lo = min(hi, max(self._fallback.min_w, live_lo, floor))
        return max(lo, min(int(value), hi))

    def set_levels(self, pl1, pl2, pl3, ac):
        if not self.supported:
            return TdpResult(pl1, None, False, "firmware-attributes path not present")
        self._set_custom_profile()
        values = {"pl1": pl1, "pl2": pl2, "pl3": pl3}
        attrs = dict(_RAIL_ATTRS)
        targets = {
            rail: self._clamp_live(values[rail], attrs[rail])
            for rail in self._rails
        }
        failed = []
        for rail in reversed(self._rails):
            attr = attrs[rail]
            if os.path.exists(self._attr(attr)) and not self._write(
                self._attr(attr),
                targets[rail],
            ):
                failed.append(f"{self.name}/{rail}")
        failed.extend(self._write_legacy(targets))
        observation = self.observe()
        mismatches = self._observation_mismatches(observation, targets)
        if not failed:
            for delay in self._readback_settle_delays:
                if not mismatches:
                    break
                time.sleep(delay)
                observation = self.observe()
                mismatches = self._observation_mismatches(
                    observation,
                    targets,
                )
        applied = observation.surfaces.get(self.name, {}).get("pl1")
        applied_w = applied.applied_w if applied else None
        problems = failed + mismatches
        return TdpResult(
            pl1,
            applied_w,
            not problems,
            "" if not problems else "write not confirmed: " + ", ".join(problems),
        )

    def set_tdp(self, watts, ac):
        # Single-value entry: write all rails flat (SPPT = FPPT = PL1). Boost headroom
        # is opt-in via set_levels, never implied by a bare TDP value.
        if not self.supported:
            return TdpResult(watts, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        target = lim.clamp(watts, ac)
        return self.set_levels(target, target, target, ac)

    def read_applied(self):
        primary = self.observe().surfaces.get(self.name, {})
        reading = primary.get("pl1")
        return reading.applied_w if reading else None

    def observe(self):
        if not self.supported:
            return TdpObservation(readable=True)
        primary = {}
        for rail, attr in _RAIL_ATTRS:
            path = self._attr(attr)
            if not os.path.exists(path):
                continue
            lo, hi = self._live_bounds(attr)
            primary[rail] = RailReading(
                self._read_int(path),
                lo,
                self._effective_live_max(rail, hi),
            )
        surfaces = {self.name: primary} if primary else {}
        legacy = {
            rail: RailReading(self._read_int(path))
            for rail, path in self._legacy.items()
        }
        if legacy:
            surfaces["asus-nb-wmi"] = legacy
        return TdpObservation(readable=True, surfaces=surfaces)

    def diagnostics(self):
        reported = {}
        for rail, attr in _RAIL_ATTRS:
            if rail not in self._rails:
                continue
            lo, hi = self._live_bounds(attr)
            reported[rail] = {"min": lo, "max": hi}
        return {
            "boost_capped_to_active": self.cap_boost_to_active,
            "ignored_live_maxes": dict(self._ignored_live_maxes),
            "readback_settle_ms": round(
                sum(self._readback_settle_delays) * 1000
            ),
            "reported_live_bounds": reported,
        }

    @staticmethod
    def _observation_mismatches(observation, targets):
        bad = []
        for surface, rails in observation.surfaces.items():
            for rail, reading in rails.items():
                target = targets.get(rail)
                if target is not None and reading.applied_w != target:
                    bad.append(f"{surface}/{rail}={reading.applied_w}")
        return bad
