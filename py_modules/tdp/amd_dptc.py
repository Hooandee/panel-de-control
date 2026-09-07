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
        safety_lock_path=None,
        ownership_lock_path=None,
    ):
        try:
            requested_max = int(write_max) if write_max is not None else 0
        except (TypeError, ValueError):
            requested_max = 0
        self._write_max = max(fallback.max_ac_w, requested_max)
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

    def _profile_rail_max(self, attr):
        if attr == "ppt_pl2_sppt":
            return round(self._write_max * 1.2)
        if attr == "ppt_pl3_fppt":
            return round(self._write_max * 1.4)
        return self._write_max
