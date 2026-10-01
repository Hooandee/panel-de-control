import glob
import os

from sysfs import read_str
from tdp.firmware_attr import FirmwareAttrBackend


class AmdDptcBackend(FirmwareAttrBackend):
    """Anatase's amd-dptc firmware ABI with cooperative state restoration."""

    def __init__(
        self,
        fallback,
        root="/",
        write_max=None,
        write_max_ac=None,
        safety_lock_path=None,
        ownership_lock_path=None,
    ):
        self._cooler_max = write_max
        self._charger_max = write_max_ac
        self._write_max = max(fallback.max_ac_w, write_max or 0, write_max_ac or 0)
        super().__init__(
            "amd-dptc",
            fallback,
            root=root,
            profile_name="amd-dptc",
            is_generic=True,
            cap_boost_to_active=True,
            safety_lock_path=safety_lock_path,
            restore_on_release=True,
            ownership_lock_path=ownership_lock_path,
        )
        self.name = "amd-dptc"
        self.supported = (
            self.supported
            and self._pp_dir is not None
            and "custom" in self.profile_choices()
        )

    def _find_profile_dir(self):
        if not self._profile_name:
            return None
        base = os.path.join(self._root, "sys/class/platform-profile")
        for candidate in sorted(glob.glob(os.path.join(base, "*"))):
            name = read_str(os.path.join(candidate, "name"))
            if name and name.startswith(self._profile_name):
                return candidate
        return None

    def set_tdp(self, watts, ac):
        if not self.supported:
            return super().set_tdp(watts, ac)
        lim = self.get_limits().with_cooler(self._cooler_max).with_ac_max(self._charger_max)
        target = lim.clamp(watts, ac)
        return self.set_levels(target, target, target, ac)

    def _profile_rail_max(self, attr):
        if attr == "ppt_pl2_sppt":
            return round(self._write_max * 1.2)
        if attr == "ppt_pl3_fppt":
            return round(self._write_max * 1.4)
        return self._write_max
