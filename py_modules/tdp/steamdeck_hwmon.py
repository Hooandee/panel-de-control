from dataclasses import dataclass
import glob
import os
import re

from sysfs import read_int, read_str, write_str
from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


_HWMON = "sys/class/hwmon"
_DECK_KEYS = {"steam_deck_lcd", "steam_deck_oled"}
_DECK_HWMON_NAME = "amdgpu"
_SLOW_COMMAND_RANGE = (3, 29)
_FAST_COMMAND_RANGE = (3, 30)
_SLOW_RESTORE_RANGE = (0, 29)
_FAST_RESTORE_RANGE = (0, 30)


@dataclass(frozen=True)
class PptApplyResult:
    ok: bool
    requested: dict
    applied: dict
    rollback: dict
    reason: str | None = None


def _watts(value):
    if value is None or value < 0:
        return None
    return round(value / 1_000_000)


def _label(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


class SteamDeckHwmonBackend(TDPBackend):
    name = "steamdeck-hwmon"
    primary_rail = "pl2"

    def __init__(self, fallback: TdpLimits, device_key: str, root: str = "/") -> None:
        self._fallback = fallback
        self._device_key = device_key
        self._root = root
        surface = self._discover()
        self._restore_surface = surface
        self._restore_identity = self._surface_identity(surface)
        self.supported = surface is not None
        self.supports_levels = bool(self.ppt_capability()["supported"])

    def _surfaces(self):
        if self._device_key not in _DECK_KEYS:
            return []
        surfaces = []
        for directory in sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*"))):
            probe = self._probe_surface(directory)
            if not probe["accepted"]:
                continue
            slow = os.path.join(directory, "power1_cap")
            fast = os.path.join(directory, "power2_cap")
            fast_valid = (
                _label(read_str(os.path.join(directory, "power2_label"))) == "fastppt"
                and read_int(fast) is not None
                and os.access(fast, os.W_OK)
            )
            surfaces.append({
                "directory": directory,
                "slow": slow,
                "fast": fast if fast_valid else None,
            })
        return surfaces

    @staticmethod
    def _probe_surface(directory):
        slow = os.path.join(directory, "power1_cap")
        fast = os.path.join(directory, "power2_cap")
        name = read_str(os.path.join(directory, "name"))
        slow_label = read_str(os.path.join(directory, "power1_label"))
        fast_label = read_str(os.path.join(directory, "power2_label"))
        slow_readable = read_int(slow) is not None
        slow_writable = os.access(slow, os.W_OK)
        if name != _DECK_HWMON_NAME:
            reason = "name_mismatch"
        elif _label(slow_label) != "slowppt":
            reason = "slow_label_mismatch"
        elif not slow_readable:
            reason = "slow_unreadable"
        elif not slow_writable:
            reason = "slow_readonly"
        else:
            reason = None
        return {
            "hwmon": os.path.basename(directory),
            "name": name,
            "slow_label": slow_label,
            "fast_label": fast_label,
            "slow_readable": slow_readable,
            "slow_writable": slow_writable,
            "fast_readable": read_int(fast) is not None,
            "fast_writable": os.access(fast, os.W_OK),
            "accepted": reason is None,
            "reason": reason,
        }

    def _discover(self):
        surfaces = self._surfaces()
        for surface in surfaces:
            capability, _ = self._surface_capability(surface)
            if capability is not None:
                return surface
        return surfaces[0] if surfaces else None

    def _surface_capability(self, surface):
        if surface["fast"] is None:
            return None, "fast_missing"
        directory = surface["directory"]
        slow_label = read_str(os.path.join(directory, "power1_label"))
        fast_label = read_str(os.path.join(directory, "power2_label"))
        if (
            (slow_label is not None and _label(slow_label) != "slowppt")
            or (fast_label is not None and _label(fast_label) != "fastppt")
        ):
            return None, "contradictory_labels"

        slow_min = _watts(read_int(os.path.join(directory, "power1_cap_min")))
        slow_max = _watts(read_int(os.path.join(directory, "power1_cap_max")))
        fast_min = _watts(read_int(os.path.join(directory, "power2_cap_min")))
        fast_max = _watts(read_int(os.path.join(directory, "power2_cap_max")))
        if (
            slow_min is not None
            and slow_max is not None
            and fast_min is not None
            and fast_max is not None
            and 0 < slow_min <= slow_max
            and 0 < fast_min <= fast_max
        ):
            slow_min = max(slow_min, _SLOW_COMMAND_RANGE[0])
            slow_max = min(slow_max, _SLOW_COMMAND_RANGE[1])
            fast_min = max(fast_min, _FAST_COMMAND_RANGE[0])
            fast_max = min(fast_max, _FAST_COMMAND_RANGE[1])
            if slow_min > slow_max or fast_min > fast_max:
                return None, "bounds_outside_safe_envelope"
            return {
                "surface": surface,
                "source": "sysfs",
                "slow": {"min": slow_min, "max": slow_max},
                "fast": {"min": fast_min, "max": fast_max},
            }, None
        if _label(slow_label) == "slowppt" and _label(fast_label) == "fastppt":
            return {
                "surface": surface,
                "source": "compatibility_override",
                "slow": {"min": self._fallback.min_w, "max": 29},
                "fast": {"min": self._fallback.min_w, "max": 30},
            }, None
        return None, "bounds_missing"

    def _capability(self):
        surfaces = self._surfaces()
        if not surfaces:
            return None, "surface_missing"
        reason = "fast_missing"
        for surface in surfaces:
            capability, candidate_reason = self._surface_capability(surface)
            if capability is not None:
                return capability, None
            reason = candidate_reason or reason
        return None, reason

    def ppt_capability(self):
        capability, _ = self._capability()
        if capability is None:
            return {
                "supported": False,
                "source": None,
                "slow": None,
                "fast": None,
                "visual_max": self._fallback.max_ac_w,
            }
        return {
            "supported": True,
            "source": capability["source"],
            "slow": capability["slow"],
            "fast": capability["fast"],
            "visual_max": capability["fast"]["max"],
        }

    def diagnostics(self):
        _, reason = self._capability()
        directories = sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*")))
        candidates = [self._probe_surface(directory) for directory in directories]
        surface = self._discover()
        return {
            "supported": self.supported,
            "backend": self.name,
            "device_key": self._device_key,
            "ppt": self.ppt_capability(),
            "ppt_reason": reason,
            "selected": (
                {
                    "hwmon": os.path.basename(surface["directory"]),
                    "name": read_str(os.path.join(surface["directory"], "name")),
                }
                if surface is not None
                else None
            ),
            "candidates": candidates,
        }

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def level_limits(self) -> dict:
        capability = self.ppt_capability()
        if not capability["supported"]:
            return {}
        return {"pl2": capability["slow"], "pl3": capability["fast"]}

    def physical_levels(self, levels: dict) -> dict[str, int]:
        if levels.get("mode") == "estable":
            stable = {"pl2": int(levels["pl1"])}
            if self.ppt_capability()["supported"]:
                stable["pl3"] = int(levels["pl1"])
            return stable
        return {"pl2": int(levels["pl2"]), "pl3": int(levels["pl3"])}

    def reconciliation_levels(self, levels: dict) -> dict[str, int]:
        return self.physical_levels(levels)

    def apply_targets(self, targets: dict[str, int], ac: bool) -> TdpResult:
        slow = int(targets["pl2"])
        if "pl3" not in targets:
            return self.set_tdp(slow, ac)
        result = self.apply_ppt(slow, int(targets["pl3"]))
        return TdpResult(
            slow,
            result.applied.get("slow"),
            result.ok,
            result.reason or "",
        )

    def _read_pair(self, surface=None):
        surface = surface or self._discover()
        if surface is None or surface["fast"] is None:
            return None
        slow = _watts(read_int(surface["slow"]))
        fast = _watts(read_int(surface["fast"]))
        return {"slow": slow, "fast": fast} if slow is not None and fast is not None else None

    def capture_ppt(self):
        pair = self._read_pair()
        return dict(pair) if pair is not None else None

    @staticmethod
    def validate_ppt_snapshot(snapshot):
        if not isinstance(snapshot, dict):
            return False
        slow = snapshot.get("slow")
        fast = snapshot.get("fast")
        return (
            not isinstance(slow, bool)
            and not isinstance(fast, bool)
            and isinstance(slow, int)
            and isinstance(fast, int)
            and slow <= fast
            and _SLOW_RESTORE_RANGE[0] <= slow <= _SLOW_RESTORE_RANGE[1]
            and _FAST_RESTORE_RANGE[0] <= fast <= _FAST_RESTORE_RANGE[1]
        )

    @staticmethod
    def _order(current, target):
        raising = target["slow"] > current["slow"] or target["fast"] > current["fast"]
        return ("fast", "slow") if raising else ("slow", "fast")

    @staticmethod
    def _path(surface, rail):
        return surface["slow" if rail == "slow" else "fast"]

    @staticmethod
    def _surface_identity(surface):
        if surface is None or surface["fast"] is None:
            return None
        try:
            slow = os.stat(surface["slow"])
            fast = os.stat(surface["fast"])
        except OSError:
            return None
        return slow.st_dev, slow.st_ino, fast.st_dev, fast.st_ino

    def _write_pair(self, surface, current, target, continue_on_failure=False):
        failures = []
        for rail in self._order(current, target):
            if not write_str(self._path(surface, rail), target[rail] * 1_000_000):
                failures.append(rail)
                if not continue_on_failure:
                    break
        return failures

    def _rollback(self, surface, current, snapshot):
        failures = self._write_pair(surface, current, snapshot, continue_on_failure=True)
        return not failures and self._read_pair(surface) == snapshot

    def apply_ppt(self, slow_w: int, fast_w: int) -> PptApplyResult:
        requested = {"slow": slow_w, "fast": fast_w}
        capability, reason = self._capability()
        if capability is None:
            return PptApplyResult(False, requested, {}, {"attempted": False, "ok": None}, reason)
        if (
            isinstance(slow_w, bool)
            or isinstance(fast_w, bool)
            or not isinstance(slow_w, int)
            or not isinstance(fast_w, int)
            or slow_w > fast_w
        ):
            return PptApplyResult(False, requested, {}, {"attempted": False, "ok": None}, "invalid_order")
        if (
            not capability["slow"]["min"] <= slow_w <= capability["slow"]["max"]
            or not capability["fast"]["min"] <= fast_w <= capability["fast"]["max"]
        ):
            return PptApplyResult(False, requested, {}, {"attempted": False, "ok": None}, "invalid_range")
        surface = capability["surface"]
        snapshot = self._read_pair(surface)
        if snapshot is None:
            return PptApplyResult(False, requested, {}, {"attempted": False, "ok": None}, "read_failed")
        failures = self._write_pair(surface, snapshot, requested)
        applied = self._read_pair(surface) or {}
        failure = f"write_{failures[0]}" if failures else None
        if failure is None and applied != requested:
            failure = "readback_mismatch"
        if failure is not None:
            rollback_ok = self._rollback(surface, applied or snapshot, snapshot)
            return PptApplyResult(
                False,
                requested,
                self._read_pair(surface) or {},
                {"attempted": True, "ok": rollback_ok},
                failure if rollback_ok else "rollback_failed",
            )
        return PptApplyResult(
            True, requested, applied, {"attempted": False, "ok": None}, None
        )

    def restore_ppt(self, snapshot) -> PptApplyResult:
        if not isinstance(snapshot, dict):
            return PptApplyResult(False, {}, {}, {"attempted": False, "ok": None}, "snapshot_invalid")
        requested = {"slow": snapshot.get("slow"), "fast": snapshot.get("fast")}
        if not self.validate_ppt_snapshot(snapshot):
            return PptApplyResult(
                False, requested, {}, {"attempted": False, "ok": None},
                "snapshot_invalid",
            )
        surface = self._discover()
        if (
            surface is None
            and self._restore_identity is not None
            and self._surface_identity(self._restore_surface) == self._restore_identity
        ):
            surface = self._restore_surface
        if surface is None or surface["fast"] is None:
            return PptApplyResult(
                False, requested, {}, {"attempted": False, "ok": None},
                "surface_missing",
            )
        current = self._read_pair(surface)
        if current is None:
            return PptApplyResult(
                False, requested, {}, {"attempted": False, "ok": None},
                "read_failed",
            )
        failures = self._write_pair(surface, current, requested)
        applied = self._read_pair(surface) or {}
        failure = f"write_{failures[0]}" if failures else None
        if failure is None and applied != requested:
            failure = "readback_mismatch"
        if failure is not None:
            rollback_ok = self._rollback(surface, applied or current, current)
            return PptApplyResult(
                False,
                requested,
                self._read_pair(surface) or {},
                {"attempted": True, "ok": rollback_ok},
                failure if rollback_ok else "rollback_failed",
            )
        return PptApplyResult(
            True, requested, applied, {"attempted": False, "ok": None}, None
        )

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        surface = self._discover()
        if surface is None:
            return TdpResult(watts, None, False, "surface_missing")
        target = self._fallback.clamp(watts, ac)
        if not write_str(surface["slow"], target * 1_000_000):
            return TdpResult(watts, self.read_applied(), False, "write_slow")
        applied = self.read_applied()
        return TdpResult(watts, applied, applied == target, "" if applied == target else "readback_mismatch")

    def read_applied(self) -> int | None:
        surface = self._discover()
        return _watts(read_int(surface["slow"])) if surface is not None else None

    def observe(self):
        surface = self._discover()
        if surface is None:
            return TdpObservation(readable=False)
        rails = {}
        slow = _watts(read_int(surface["slow"]))
        if slow is not None:
            capability = self.ppt_capability()
            bounds = capability["slow"] if capability["supported"] else {
                "min": self._fallback.min_w,
                "max": self._fallback.max_ac_w,
            }
            rails["pl2"] = RailReading(slow, bounds["min"], bounds["max"])
        if surface["fast"] is not None:
            fast = _watts(read_int(surface["fast"]))
            capability = self.ppt_capability()
            if fast is not None and capability["supported"]:
                rails["pl3"] = RailReading(
                    fast, capability["fast"]["min"], capability["fast"]["max"]
                )
        surfaces = {self.name: rails} if rails else {}
        return TdpObservation(readable=True, surfaces=surfaces)
