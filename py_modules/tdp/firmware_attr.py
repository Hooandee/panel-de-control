import glob
import os

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_FW_BASE = "sys/class/firmware-attributes"
_PP_BASE = "sys/class/platform-profile"


class FirmwareAttrBackend(TDPBackend):
    """TDP via kernel firmware-attributes. Covers ASUS (asus-armoury), Lenovo
    (lenovo-wmi-other), MSI (msi-wmi-platform): ppt_pl1_spl/ppt_pl2_sppt/ppt_pl3_fppt
    with current_value (watts) + min_value/max_value. Never raises."""

    supports_levels = True

    def __init__(self, driver_prefix, fallback, root="/", profile_name=None):
        self.name = f"firmware-attr:{driver_prefix}"
        self._fallback = fallback
        self._root = root
        self._profile_name = profile_name  # Lenovo: set this platform-profile to "custom" first
        self._dir = self._find_driver_dir(driver_prefix)
        self.supported = self._dir is not None and os.path.exists(self._attr("ppt_pl1_spl"))

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
        mn = self._read_int(self._attr("ppt_pl1_spl", "min_value"))
        mx = self._read_int(self._attr("ppt_pl1_spl", "max_value"))
        min_w = mn if mn is not None else self._fallback.min_w
        max_w = mx if mx is not None else self._fallback.max_w
        default_w = max(min_w, min(self._fallback.default_w, max_w))
        return TdpLimits(min_w=min_w, default_w=default_w, max_w=max_w, max_ac_w=max_w)

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
        mn = self._read_int(self._attr(attr, "min_value"))
        mx = self._read_int(self._attr(attr, "max_value"))
        return mn, mx

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
        if not self.supported:
            return TdpResult(watts, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        target = lim.clamp(watts)
        pl2 = max(target, round(target * 1.2))
        pl3 = max(target, round(target * 1.4))
        return self.set_levels(target, pl2, pl3, ac)

    def read_applied(self):
        return self._read_int(self._attr("ppt_pl1_spl"))
