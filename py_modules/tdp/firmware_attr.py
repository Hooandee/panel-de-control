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

    def set_tdp(self, watts, ac):
        if not self.supported:
            return TdpResult(watts, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        target = lim.clamp(watts)
        self._set_custom_profile()
        # boost headroom for pl2/pl3, clamped to their own sysfs maxima
        pl2_max = self._read_int(self._attr("ppt_pl2_sppt", "max_value"))
        pl3_max = self._read_int(self._attr("ppt_pl3_fppt", "max_value"))
        pl2 = target if pl2_max is None else min(pl2_max, max(target, round(target * 1.2)))
        pl3 = target if pl3_max is None else min(pl3_max, max(target, round(target * 1.4)))
        # write boost first, sustained (pl1) LAST
        self._write(self._attr("ppt_pl3_fppt"), pl3)
        self._write(self._attr("ppt_pl2_sppt"), pl2)
        ok = self._write(self._attr("ppt_pl1_spl"), target)
        applied = self.read_applied()
        success = ok and applied == target
        detail = "" if success else f"write not confirmed (wanted {target}, read {applied})"
        return TdpResult(watts, applied, success, detail)

    def read_applied(self):
        return self._read_int(self._attr("ppt_pl1_spl"))
