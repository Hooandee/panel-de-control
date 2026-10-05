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
        rail_max_ac=None,
        safety_lock_path=None,
        ownership_lock_path=None,
    ):
        self._rail_ceiling = max(fallback.max_ac_w, write_max or 0, rail_max_ac or 0)
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
            write_max_ac=write_max_ac,
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

    def _profile_rail_max(self, attr):
        if attr == "ppt_pl2_sppt":
            return round(self._rail_ceiling * 1.2)
        if attr == "ppt_pl3_fppt":
            return round(self._rail_ceiling * 1.4)
        return self._rail_ceiling
