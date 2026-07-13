import glob
import os

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_FW_BASE = "sys/class/firmware-attributes"
_PP_BASE = "sys/class/platform-profile"

# Boost headroom derived from sustained PL1 when the user sets a single TDP value.
# PL2 (slow) and PL3 (fast) are scaled above PL1, then clamped to each rail's sysfs max.
_PL2_BOOST_RATIO = 1.2
_PL3_BOOST_RATIO = 1.4

# Guard against bogus firmware ppt ceilings (some ASUS kernels report every rail as
# 150 W). A recognised device trusts its sysfs PL1 max only within this margin of the
# profile charger max; beyond that the whole ppt set is untrusted and all rails fall
# back to profile-derived maxes. A generic device has no reference, so it only drops a
# physically-impossible value per rail.
_FW_MARGIN_W = 10
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
        self._bounds = {}  # attr -> (min, max); static hardware limits, read once
        if self.supported:
            for attr in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
                self._bounds[attr] = (
                    self._read_int(self._attr(attr, "min_value")),
                    self._read_int(self._attr(attr, "max_value")),
                )
            self._sanitize_bounds()

    def _sanitize_bounds(self):
        """Drop bogus firmware rail ceilings so a lying kernel never exposes a
        dangerous slider (base OR boost). If the sustained PL1 max is implausible on a
        recognised device (beyond the profile charger max + margin), the whole ppt set
        is untrusted → rebuild all maxes from the profile (PL1 = charger max, boost
        rails scaled from it). A trustworthy firmware keeps its real per-rail maxes
        (legitimate boost above PL1). A generic device only drops an impossible value."""
        mx1 = self._bounds.get("ppt_pl1_spl", (None, None))[1]
        if mx1 is None:
            return
        if self._is_generic:
            for attr, (lo, hi) in self._bounds.items():
                if hi is not None and hi > _FW_ABSURD_W:
                    self._bounds[attr] = (lo, _FW_ABSURD_W)
            return
        ceil = self._fallback.max_ac_w
        if mx1 <= ceil + _FW_MARGIN_W:
            return  # trustworthy — keep real per-rail maxes
        for attr, ratio in (("ppt_pl1_spl", 1.0),
                            ("ppt_pl2_sppt", _PL2_BOOST_RATIO),
                            ("ppt_pl3_fppt", _PL3_BOOST_RATIO)):
            lo = self._bounds.get(attr, (None, None))[0]
            self._bounds[attr] = (lo, round(ceil * ratio))

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
        mn, mx = self._pl_bounds("ppt_pl1_spl")  # already sanitized in _sanitize_bounds
        min_w = mn if mn is not None else self._fallback.min_w
        fw_max = mx if mx is not None else self._fallback.max_ac_w  # firmware (charger) ceiling
        batt_max = min(self._fallback.max_w, fw_max)                # device battery policy
        default_w = max(min_w, min(self._fallback.default_w, fw_max))
        return TdpLimits(min_w=min_w, default_w=default_w, max_w=batt_max, max_ac_w=fw_max)

    def _set_custom_profile(self):
        if not self._profile_name:
            return
        base = os.path.join(self._root, _PP_BASE)
        for d in glob.glob(os.path.join(base, "*")):
            try:
                with open(os.path.join(d, "name")) as f:
                    if f.read().strip() == self._profile_name:
                        self._write(os.path.join(d, "profile"), "custom")
                        return
            except OSError:
                continue

    def _pl_bounds(self, attr):
        return self._bounds.get(attr, (None, None))

    def level_limits(self):
        out = {}
        for key, attr in (("pl1", "ppt_pl1_spl"), ("pl2", "ppt_pl2_sppt"), ("pl3", "ppt_pl3_fppt")):
            mn, mx = self._pl_bounds(attr)
            if mn is not None and mx is not None:
                out[key] = {"min": mn, "max": mx}
        return out

    def _clamp(self, value, attr, fallback_min, fallback_max):
        mn, mx = self._pl_bounds(attr)
        lo = mn if mn is not None else fallback_min
        hi = mx if mx is not None else fallback_max
        return max(lo, min(int(value), hi))

    def set_levels(self, pl1, pl2, pl3, ac):
        if not self.supported:
            return TdpResult(pl1, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        c1 = self._clamp(pl1, "ppt_pl1_spl", lim.min_w, lim.max_ac_w)
        c2 = self._clamp(pl2, "ppt_pl2_sppt", lim.min_w, lim.max_ac_w)
        c3 = self._clamp(pl3, "ppt_pl3_fppt", lim.min_w, lim.max_ac_w)
        self._set_custom_profile()
        self._write(self._attr("ppt_pl3_fppt"), c3)
        self._write(self._attr("ppt_pl2_sppt"), c2)
        ok = self._write(self._attr("ppt_pl1_spl"), c1)
        applied = self.read_applied()
        success = ok and applied == c1
        detail = "" if success else f"write not confirmed (wanted {c1}, read {applied})"
        return TdpResult(pl1, applied, success, detail)

    def set_tdp(self, watts, ac):
        # Single-value entry: write all rails flat (SPPT = FPPT = PL1). Boost headroom
        # is opt-in via set_levels, never implied by a bare TDP value.
        if not self.supported:
            return TdpResult(watts, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        target = lim.clamp(watts, ac)
        return self.set_levels(target, target, target, ac)

    def read_applied(self):
        return self._read_int(self._attr("ppt_pl1_spl"))
