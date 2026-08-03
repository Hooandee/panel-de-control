from dataclasses import dataclass
import glob
import os
import re

from sysfs import read_int, read_str, write_str
from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


_HWMON = "sys/class/hwmon"
_DECK_KEYS = {"steam_deck_lcd", "steam_deck_oled"}


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
        self.supported = surface is not None
        self.supports_levels = bool(self.ppt_capability()["supported"])

    def _discover(self):
        if self._device_key not in _DECK_KEYS:
            return None
        for directory in sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*"))):
            if read_str(os.path.join(directory, "name")) != "amdgpu":
                continue
            slow = os.path.join(directory, "power1_cap")
            if read_int(slow) is None or not os.access(slow, os.W_OK):
                continue
            fast = os.path.join(directory, "power2_cap")
            return {
                "directory": directory,
                "slow": slow,
                "fast": fast if read_int(fast) is not None and os.access(fast, os.W_OK) else None,
            }
        return None

    def _capability(self):
        surface = self._discover()
        if surface is None:
            return None, "surface_missing"
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
        return {
            "supported": self.supported,
            "backend": self.name,
            "device_key": self._device_key,
            "ppt": self.ppt_capability(),
            "ppt_reason": reason,
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
            return {"pl2": int(levels["pl1"])}
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
    def _order(current, target):
        raising = target["slow"] > current["slow"] or target["fast"] > current["fast"]
        return ("fast", "slow") if raising else ("slow", "fast")

    @staticmethod
    def _path(surface, rail):
        return surface["slow" if rail == "slow" else "fast"]

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
        return self.apply_ppt(snapshot.get("slow"), snapshot.get("fast"))

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
