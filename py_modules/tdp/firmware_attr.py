import glob
import os

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

# Guard against a bogus firmware ppt ceiling on a generic device (some ASUS kernels
# report every rail as 150 W). A recognised device uses its profile, not this.
_FW_ABSURD_W = 100


class FirmwareAttrBackend(TDPBackend):
    """TDP via kernel firmware-attributes. Covers ASUS (asus-armoury), Lenovo
    (lenovo-wmi-other), MSI (msi-wmi-platform): ppt_pl1_spl/ppt_pl2_sppt/ppt_pl3_fppt
    with current_value (watts) + min_value/max_value. Never raises."""

    supports_levels = True

    def __init__(self, driver_prefix, fallback, root="/", profile_name=None, is_generic=False):
        self.name = f"firmware-attr:{driver_prefix}"
        self._fallback = fallback
        self._root = root
        self._profile_name = profile_name  # Lenovo: set this platform-profile to "custom" first
        self._is_generic = is_generic
        self._dir = self._find_driver_dir(driver_prefix)
        self.supported = self._dir is not None and os.path.exists(self._attr("ppt_pl1_spl"))
        self._pp_dir = self._find_profile_dir()  # static, resolved once
        self._pp_choices = None                  # parsed lazily, then cached
        self._legacy = self._find_legacy_nodes(driver_prefix)  # ASUS dual-interface

    def _live_bounds(self, attr):
        # Read live, never cache: the firmware ceiling is dynamic (lower on battery,
        # momentarily low on Lenovo) and caching it froze a bad read. Generic devices
        # get a sanity cap; recognised ones take their range from the profile instead.
        lo = self._read_int(self._attr(attr, "min_value"))
        hi = self._read_int(self._attr(attr, "max_value"))
        if self._is_generic and hi is not None and hi > _FW_ABSURD_W:
            hi = _FW_ABSURD_W
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

    def _write_legacy(self, pl1, pl2, pl3):
        failed = []
        for rail, val in (("pl3", pl3), ("pl2", pl2), ("pl1", pl1)):
            path = self._legacy.get(rail)
            if path and not self._write(path, val):
                failed.append(f"asus-nb-wmi/{rail}")
        return failed

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
        # Generic device: no profile to trust, so take the firmware's live ceiling.
        mn, mx = self._live_bounds("ppt_pl1_spl")
        min_w = mn if mn is not None else self._fallback.min_w
        fw_max = mx if mx is not None else self._fallback.max_ac_w
        default_w = max(min_w, min(self._fallback.default_w, fw_max))
        return TdpLimits(min_w=min_w, default_w=default_w, max_w=fw_max, max_ac_w=fw_max)

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
            for key, attr in (("pl1", "ppt_pl1_spl"), ("pl2", "ppt_pl2_sppt"), ("pl3", "ppt_pl3_fppt")):
                mn, mx = self._live_bounds(attr)
                if mn is not None and mx is not None:
                    out[key] = {"min": mn, "max": mx}
            return out
        # Recognised: rails from the profile (PL1 = charger max, boost scaled); writes
        # clamp to the live ceiling anyway.
        mn, mx = self._fallback.min_w, self._fallback.max_ac_w
        return {
            "pl1": {"min": mn, "max": mx},
            "pl2": {"min": mn, "max": round(mx * _PL2_BOOST_RATIO)},
            "pl3": {"min": mn, "max": round(mx * _PL3_BOOST_RATIO)},
        }

    def _profile_rail_max(self, attr):
        """Recognised-device write ceiling for a rail, mirroring level_limits(): PL1 =
        charger max, boost rails profile-scaled. The profile is the authority — not the
        firmware's reported max, which some ASUS kernels report as a bogus 150 W."""
        mx = self._fallback.max_ac_w
        if attr == "ppt_pl2_sppt":
            return round(mx * _PL2_BOOST_RATIO)
        if attr == "ppt_pl3_fppt":
            return round(mx * _PL3_BOOST_RATIO)
        return mx

    def _clamp_live(self, value, attr):
        mn, mx = self._live_bounds(attr)
        lo = mn if mn is not None else self._fallback.min_w
        hi = mx if mx is not None else self._fallback.max_ac_w
        if not self._is_generic:
            # Bound the write to the profile ceiling too, keeping the LOWER of the two:
            # the live firmware max still applies the dynamic battery/charger ceiling,
            # but a bogus-high firmware read (150 W) can never leak into a write and
            # cook the machine.
            hi = min(hi, self._profile_rail_max(attr))
        return max(lo, min(int(value), hi))

    def set_levels(self, pl1, pl2, pl3, ac):
        if not self.supported:
            return TdpResult(pl1, None, False, "firmware-attributes path not present")
        # Custom mode first (Lenovo prestep), then clamp each rail to the LIVE ceiling:
        # writing above it is rejected, so the applied value follows what the firmware
        # accepts now (25 W on battery, 30 W on charger) while the profile range stays put.
        self._set_custom_profile()
        c1 = self._clamp_live(pl1, "ppt_pl1_spl")
        c2 = self._clamp_live(pl2, "ppt_pl2_sppt")
        c3 = self._clamp_live(pl3, "ppt_pl3_fppt")
        targets = {"pl1": c1, "pl2": c2, "pl3": c3}
        failed = []
        for rail, attr, value in (
            ("pl3", "ppt_pl3_fppt", c3),
            ("pl2", "ppt_pl2_sppt", c2),
            ("pl1", "ppt_pl1_spl", c1),
        ):
            if not self._write(self._attr(attr), value):
                failed.append(f"{self.name}/{rail}")
        failed.extend(self._write_legacy(c1, c2, c3))
        observation = self.observe()
        mismatches = self._observation_mismatches(observation, targets)
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
            primary[rail] = RailReading(self._read_int(path), lo, hi)
        surfaces = {self.name: primary} if primary else {}
        legacy = {
            rail: RailReading(self._read_int(path))
            for rail, path in self._legacy.items()
        }
        if legacy:
            surfaces["asus-nb-wmi"] = legacy
        return TdpObservation(readable=True, surfaces=surfaces)

    @staticmethod
    def _observation_mismatches(observation, targets):
        bad = []
        for surface, rails in observation.surfaces.items():
            for rail, reading in rails.items():
                target = targets.get(rail)
                if target is not None and reading.applied_w != target:
                    bad.append(f"{surface}/{rail}={reading.applied_w}")
        return bad
