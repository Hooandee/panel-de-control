import os

from sysfs import read_str
from tdp.firmware_attr import FirmwareAttrBackend, _RAIL_ATTRS


class MsiClawA8FirmwareBackend(FirmwareAttrBackend):
    """MSI Claw A8 firmware ABI, gated to its exact board identifier."""

    def __init__(
        self,
        fallback,
        root="/",
        safety_lock_path=None,
        ownership_lock_path=None,
        write_max_ac=None,
    ):
        super().__init__(
            "msi-wmi-platform",
            fallback,
            root=root,
            is_generic=True,
            write_max_ac=write_max_ac,
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

    def _zero_ownership_baseline(self, payload):
        return (
            read_str(os.path.join(self._root, "sys/class/dmi/id/board_name")) == "MS-1T8K"
            and isinstance(payload, dict)
            and payload.get("profile") is None
            and payload.get("snapshot") == {
                f"{self.name}/{rail}": 0 for rail, _attr in _RAIL_ATTRS
            }
            and all(type(value) is int for value in payload["snapshot"].values())
        )

    def ownership_resume_ready(self):
        if (
            not self.supported
            or self._runtime_lock_payload is not None
            or not self._ownership_recovery_pending
            or not self._zero_ownership_baseline(self._owned_payload)
            or self._owned_payload.get("state") not in ("ownership_pending", "rollback_failed")
        ):
            return False
        for _rail, attr in _RAIL_ATTRS:
            lo, hi = self._live_bounds(attr)
            current = self._read_int(self._attr(attr))
            if (
                lo is None or hi is None or lo <= 0 or hi < lo
                or current is None or not lo <= current <= hi
            ):
                return False
        return True

    def _capture_transaction(self, surfaces):
        snapshot, profile, missing = super()._capture_transaction(surfaces)
        if self._owns_state and self._zero_ownership_baseline(self._owned_payload):
            attrs = dict(_RAIL_ATTRS)
            for surface, rail, path in surfaces:
                lo, hi = self._live_bounds(attrs[rail])
                value = snapshot.get(path)
                if (
                    lo is None or hi is None or lo <= 0 or hi < lo
                    or value is None or not lo <= value <= hi
                ):
                    missing.append(f"{self._surface_label(surface, rail)}=unrestorable")
        return snapshot, profile, missing

    def resume_ownership(self, write_authorized=False):
        if not write_authorized or not self.ownership_resume_ready():
            return {"ok": False, "detail": "firmware ownership resume not authorized or ready"}
        # Keep the original marker: continuing control does not restore the boot state.
        self._ownership_recovery_pending = False
        self._owns_state = True
        self._write_circuit_open = None
        return {"ok": True, "detail": "firmware ownership resumed; original restore pending"}

    def _restore_payload(self, purpose):
        payload = self._owned_payload if purpose == "ownership" else self._runtime_lock_payload
        if self._zero_ownership_baseline(payload):
            detail = f"firmware {purpose} restore pending: zero snapshot is not writable"
            self._write_circuit_open = detail
            if purpose == "ownership":
                self._ownership_recovery_pending = True
                self._owns_state = False
            return {"ok": False, "detail": detail}
        return super()._restore_payload(purpose)

    def relinquish_ownership(self):
        if self._zero_ownership_baseline(self._owned_payload):
            return {"ok": False, "detail": "firmware ownership original restore pending"}
        return super().relinquish_ownership()

    def diagnostics(self):
        detail = super().diagnostics()
        payload = self._owned_payload
        if isinstance(payload, dict):
            saved = payload.get("snapshot")
            saved = saved if isinstance(saved, dict) else {}
            snapshot = {}
            for rail, _attr in _RAIL_ATTRS:
                value = saved.get(f"{self.name}/{rail}")
                if type(value) is int and abs(value) <= 1000:
                    snapshot[rail] = value
            state = payload.get("state")
            detail["ownership_lock"] = {
                "state": state if state in ("ownership_pending", "rollback_failed") else "unknown",
                "snapshot": snapshot,
            }
            profile = payload.get("profile")
            if profile is None or profile in (
                "low-power", "balanced", "balanced-performance", "performance", "custom",
            ):
                detail["ownership_lock"]["profile"] = profile
            detail["ownership_restore_pending"] = self._zero_ownership_baseline(payload)
        return detail

    def get_limits(self):
        return self._fallback

    def _profile_rail_max(self, attr):
        if attr == "ppt_pl2_sppt":
            return 37
        if attr == "ppt_pl3_fppt":
            return 55
        return self._fallback.max_ac_w
