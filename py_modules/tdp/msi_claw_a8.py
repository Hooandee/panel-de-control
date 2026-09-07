import os

from sysfs import read_str
from tdp.firmware_attr import FirmwareAttrBackend


class MsiClawA8FirmwareBackend(FirmwareAttrBackend):
    """MSI Claw A8 firmware ABI, gated to its exact board identifier."""

    def __init__(
        self,
        fallback,
        root="/",
        safety_lock_path=None,
        ownership_lock_path=None,
    ):
        super().__init__(
            "msi-wmi-platform",
            fallback,
            root=root,
            is_generic=True,
            safety_lock_path=safety_lock_path,
            restore_on_release=True,
            ownership_lock_path=ownership_lock_path,
        )
        self.name = "msi-claw-a8-firmware"
        self.supported = (
            read_str(os.path.join(root, "sys/class/dmi/id/board_name")) == "MS-1T8K"
            and self._dir is not None
            and len(self._primary_rails) == 3
        )
        self.supports_levels = self.supported

    def get_limits(self):
        return self._fallback

    def _profile_rail_max(self, attr):
        if attr == "ppt_pl2_sppt":
            return 37
        if attr == "ppt_pl3_fppt":
            return 55
        return self._fallback.max_ac_w
