import os

from tdp.backend import TDPBackend
from tdp.runtime_lock import RuntimeSafetyLock
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


_BASE = "sys/devices/platform/asus-nb-wmi"
_NODES = (
    ("pl1", "ppt_pl1_spl"),
    ("pl2", "ppt_pl2_sppt"),
    ("pl3", "ppt_fppt"),
)


class AsusNbWmiBackend(TDPBackend):
    """Standalone legacy ASUS TDP ABI used when asus-armoury is absent."""

    name = "asus-nb-wmi"
    reselection_safe_after_use = True
    low_battery_hold_strategy = "primary"

    def __init__(
        self,
        fallback: TdpLimits,
        root: str = "/",
        ownership_lock_path: str | None = None,
    ) -> None:
        self._fallback = fallback
        base = os.path.join(root, _BASE)
        self._paths = {
            rail: os.path.join(base, node)
            for rail, node in _NODES
            if os.path.isfile(os.path.join(base, node))
        }
        self._rails = tuple(rail for rail, _node in _NODES if rail in self._paths)
        self.supported = "pl1" in self._paths
        self.supports_levels = len(self._rails) > 1
        self._ownership_lock = RuntimeSafetyLock(ownership_lock_path)
        payload = self._ownership_lock.load_payload()
        saved = payload.get("snapshot") if isinstance(payload, dict) else None
        self._owned_snapshot = (
            {rail: int(value) for rail, value in saved.items()}
            if isinstance(saved, dict)
            and set(saved) == set(self._rails)
            and all(isinstance(value, int) for value in saved.values())
            else None
        )
        self._ownership_recovery_pending = payload is not None
        self._recovery_blocked = False
        self._selection_failure = {}

    @property
    def safety_locked(self) -> bool:
        return self._recovery_blocked or self._ownership_recovery_pending

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def level_limits(self) -> dict:
        return {
            rail: {
                "min": self._fallback.min_w,
                "max": self._rail_max(rail),
            }
            for rail in self._rails
        }

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "asus-nb-wmi TDP path not present")
        target = self._fallback.clamp(watts, ac)
        return self.set_levels(target, target, target, ac)

    def set_levels(self, pl1: int, pl2: int, pl3: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(pl1, None, False, "asus-nb-wmi TDP path not present")
        if self.safety_locked:
            return TdpResult(pl1, self.read_applied(), False, "TDP recovery pending")
        requested = {"pl1": pl1, "pl2": pl2, "pl3": pl3}
        targets = {
            rail: max(
                self._fallback.min_w,
                min(int(requested[rail]), self._rail_max(rail)),
            )
            for rail in self._rails
        }
        before = self._read_snapshot()
        if before is None:
            return TdpResult(pl1, self.read_applied(), False, "TDP snapshot unavailable")
        first_claim = self._owned_snapshot is None
        if first_claim:
            payload = {
                "state": "ownership_pending",
                "snapshot": before,
            }
            if not self._ownership_lock.persist_payload(payload):
                return TdpResult(
                    pl1,
                    self.read_applied(),
                    False,
                    "ownership safety lock unavailable; no writes performed",
                )
            self._owned_snapshot = before

        failure = self._write_and_verify(targets)
        if failure is not None:
            restored = self._restore(before)
            if restored and first_claim:
                if not self._ownership_lock.clear():
                    self._recovery_blocked = True
                    return TdpResult(
                        pl1,
                        self.read_applied(),
                        False,
                        f"write not confirmed: {failure}, recovery marker clear failed",
                    )
                self._owned_snapshot = None
            self._recovery_blocked = not restored
            detail = f"write not confirmed: {failure}"
            detail += ", rolled back" if restored else ", rollback failed"
            return TdpResult(pl1, self.read_applied(), False, detail)

        return TdpResult(pl1, targets["pl1"], True, "")

    def read_applied(self) -> int | None:
        return self._read_int(self._paths.get("pl1"))

    def observe(self) -> TdpObservation:
        surfaces = (
            {
                self.name: {
                    rail: RailReading(
                        self._read_int(path),
                        self._fallback.min_w,
                        self._rail_max(rail),
                    )
                    for rail, path in self._paths.items()
                }
            }
            if self.supported
            else {}
        )
        return TdpObservation(readable=self.supported, surfaces=surfaces)

    def reconciliation_levels(self, levels: dict) -> dict[str, int]:
        return {
            rail: int(levels[rail])
            for rail in self._rails
            if rail in levels
        }

    def ready(self) -> bool:
        return self.selection_ready()

    def probe(self) -> bool:
        return self.ready()

    def selection_ready(self) -> bool:
        self._selection_failure = {}
        if not self.supported:
            self._selection_failure = {"unready_reason": "not_present"}
            return False
        if self.safety_locked:
            self._selection_failure = {"unready_reason": "ownership_recovery"}
            return False
        unavailable = [
            f"{self.name}/{rail}=unavailable"
            for rail, path in self._paths.items()
            if self._read_int(path) is None
        ]
        if unavailable:
            self._selection_failure = {
                "unready_reason": "snapshot_unavailable",
                "unavailable": unavailable,
            }
            return False
        return True

    def selection_diagnostics(self) -> dict:
        return dict(self._selection_failure)

    def release(self) -> bool:
        if self._owned_snapshot is None:
            return not self.safety_locked
        restored = self._restore(self._owned_snapshot)
        self._recovery_blocked = not restored
        if restored:
            if not self._ownership_lock.clear():
                self._recovery_blocked = True
                return False
            self._owned_snapshot = None
            self._ownership_recovery_pending = False
        return restored

    def recover_runtime_transaction(self) -> dict:
        if not self._ownership_recovery_pending:
            return {"ok": True, "detail": "no ASUS legacy recovery pending"}
        if self._owned_snapshot is None:
            return {"ok": False, "detail": "ASUS legacy recovery snapshot invalid"}
        ok = self.release()
        return {
            "ok": ok,
            "detail": (
                "ASUS legacy ownership recovered"
                if ok
                else "ASUS legacy ownership recovery failed"
            ),
        }

    def relinquish_ownership(self) -> dict:
        if self._recovery_blocked:
            return {"ok": False, "detail": "ASUS legacy recovery blocked"}
        if not self._ownership_recovery_pending:
            return {"ok": True, "detail": "no ASUS legacy ownership pending"}
        if self._owned_snapshot is None:
            return {"ok": False, "detail": "ASUS legacy recovery snapshot invalid"}
        if not self._ownership_lock.clear():
            return {"ok": False, "detail": "ASUS legacy ownership marker clear failed"}
        self._owned_snapshot = None
        self._ownership_recovery_pending = False
        return {"ok": True, "detail": "ASUS legacy ownership relinquished"}

    def diagnostics(self) -> dict:
        diagnostics = {
            "rails": list(self._rails),
            "transactional": True,
            "owns_state": self._owned_snapshot is not None,
            "recovery_blocked": self.safety_locked,
        }
        if self._selection_failure:
            diagnostics["selection_failure"] = dict(self._selection_failure)
        return diagnostics

    def _rail_max(self, rail: str) -> int:
        if rail == "pl2":
            return round(self._fallback.max_ac_w * 1.2)
        if rail == "pl3":
            return round(self._fallback.max_ac_w * 1.4)
        return self._fallback.max_ac_w

    def _read_snapshot(self) -> dict[str, int] | None:
        values = {rail: self._read_int(path) for rail, path in self._paths.items()}
        if any(value is None for value in values.values()):
            return None
        return {rail: int(value) for rail, value in values.items()}

    def _write_and_verify(self, values: dict[str, int]) -> str | None:
        for rail in reversed(self._rails):
            if not self._write(self._paths[rail], values[rail]):
                return f"{self.name}/{rail} write failed"
        for rail in self._rails:
            observed = self._read_int(self._paths[rail])
            if observed != values[rail]:
                shown = "unavailable" if observed is None else observed
                return f"{self.name}/{rail}={shown}"
        return None

    def _restore(self, values: dict[str, int]) -> bool:
        writes = [
            self._write(self._paths[rail], values[rail])
            for rail in reversed(self._rails)
        ]
        return all(writes) and all(
            self._read_int(self._paths[rail]) == values[rail]
            for rail in self._rails
        )

    @staticmethod
    def _read_int(path: str | None) -> int | None:
        if not path:
            return None
        try:
            with open(path) as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write(path: str, value: int) -> bool:
        try:
            with open(path, "w") as handle:
                handle.write(f"{value}\n")
            return True
        except OSError:
            return False
