import os

from tdp.backend import TDPBackend
from tdp.runtime_lock import RuntimeSafetyLock
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult

_POWERCAP = "sys/devices/virtual/powercap"
# Prefer the MMIO interface (current on recent kernels), fall back to the legacy one.
_RAPL_SURFACES = (
    ("mmio", "intel-rapl-mmio/intel-rapl-mmio:0"),
    ("msr", "intel-rapl/intel-rapl:0"),
)
_RAPL_NAMES = {"long_term": "pl1", "short_term": "pl2"}
_CLAW_PL2_RESTORE_MAX_W = 37


class IntelRaplBackend(TDPBackend):
    """Intel handheld TDP control through the kernel powercap RAPL interface."""

    name = "intel-rapl"
    supports_levels = False
    auto_tdp_safe = False
    read_tolerance_w = 1
    low_battery_hold_strategy = "primary"

    def __init__(
        self,
        fallback: TdpLimits,
        root: str = "/",
        safety_lock_path: str | None = None,
        ownership_lock_path: str | None = None,
        auto_tdp_allowed: bool = True,
    ) -> None:
        self._fallback = fallback
        self._root = root
        self._safety_lock = RuntimeSafetyLock(safety_lock_path)
        self._ownership_lock = RuntimeSafetyLock(ownership_lock_path)
        self._dir = self._find_rapl_dir()
        self.supported = self._dir is not None
        self._auto_surfaces = self._find_auto_surfaces()
        self.auto_tdp_safe = bool(auto_tdp_allowed) and (
            len(self._auto_surfaces) == len(_RAPL_SURFACES)
        )
        self._runtime_lock_payload = self._safety_lock.load_payload()
        self._owned_payload = self._ownership_lock.load_payload()
        self._owns_state = False
        self._ownership_recovery_pending = self._owned_payload is not None
        self._write_circuit_open = (
            self._runtime_lock_payload.get("detail")
            if self._runtime_lock_payload
            else None
        )

    def _find_rapl_dir(self):
        for _label, base in _RAPL_SURFACES:
            d = os.path.join(self._root, _POWERCAP, base)
            if os.path.exists(os.path.join(d, "constraint_0_power_limit_uw")):
                return d
        return None

    def _find_auto_surfaces(self):
        surfaces = {}
        for label, base in _RAPL_SURFACES:
            directory = os.path.join(self._root, _POWERCAP, base)
            if self._read_text(os.path.join(directory, "name")) != "package-0":
                continue
            constraints = {}
            for index in range(8):
                name = self._read_text(
                    os.path.join(directory, f"constraint_{index}_name")
                )
                if name in _RAPL_NAMES:
                    limit = os.path.join(
                        directory,
                        f"constraint_{index}_power_limit_uw",
                    )
                    if self._read_int(limit) is not None and os.access(
                        limit,
                        os.W_OK,
                    ):
                        constraints[_RAPL_NAMES[name]] = limit
            if set(constraints) == {"pl1", "pl2"}:
                surfaces[label] = constraints
        return surfaces

    def _auto_paths(self):
        return {
            f"{surface}/{rail}": path
            for surface, rails in self._auto_surfaces.items()
            for rail, path in rails.items()
        }

    def _capture_auto_snapshot(self):
        snapshot = {}
        missing = []
        for label, path in self._auto_paths().items():
            value = self._read_int(path)
            if value is None:
                missing.append(label)
            else:
                snapshot[label] = value
        return snapshot, missing

    def _ordered_labels(self, targets):
        paths = self._auto_paths()
        raising = any(
            (current := self._read_int(paths[label])) is None
            or int(target) > current
            for label, target in targets.items()
        )
        rails = ("pl2", "pl1") if raising else ("pl1", "pl2")
        return [
            label
            for rail in rails
            for label in paths
            if label.endswith(f"/{rail}")
        ]

    def _write_and_verify_snapshot(self, snapshot):
        paths = self._auto_paths()
        if set(snapshot) != set(paths):
            return False, ["RAPL surfaces changed"]
        problems = []
        for label in self._ordered_labels(snapshot):
            if not self._write(paths[label], int(snapshot[label])):
                problems.append(f"{label}=write-failed")
                break
        for label, target in snapshot.items():
            value = self._read_int(paths[label])
            if value is None or abs(round(value / 1_000_000) - round(int(target) / 1_000_000)) > self.read_tolerance_w:
                problems.append(f"{label}=unconfirmed")
        return not problems, problems

    def _snapshot_valid(self, snapshot):
        if set(snapshot) != set(self._auto_paths()):
            return False
        minimum = self._fallback.min_w * 1_000_000
        maximum = {
            "pl1": self._fallback.max_ac_w * 1_000_000,
            "pl2": max(
                self._fallback.max_ac_w,
                _CLAW_PL2_RESTORE_MAX_W,
            )
            * 1_000_000,
        }
        if any(
            not minimum <= value <= maximum[label.rsplit("/", 1)[1]]
            for label, value in snapshot.items()
        ):
            return False
        return all(
            snapshot[f"{surface}/pl2"] >= snapshot[f"{surface}/pl1"]
            for surface in ("mmio", "msr")
        )

    def _restore_payload(self, purpose):
        payload = (
            self._runtime_lock_payload
            if purpose == "transaction"
            else self._owned_payload
        )
        snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
        if not isinstance(snapshot, dict) or not snapshot:
            return {"ok": False, "detail": f"RAPL {purpose} snapshot unavailable"}
        try:
            normalized = {label: int(value) for label, value in snapshot.items()}
        except (TypeError, ValueError):
            return {"ok": False, "detail": f"RAPL {purpose} snapshot invalid"}
        if not self._snapshot_valid(normalized):
            return {"ok": False, "detail": f"RAPL {purpose} snapshot invalid"}
        restored, problems = self._write_and_verify_snapshot(normalized)
        lock = self._safety_lock if purpose == "transaction" else self._ownership_lock
        if not restored:
            detail = f"RAPL {purpose} recovery failed: " + ", ".join(problems)
            failed_payload = {**payload, "state": "rollback_failed", "detail": detail}
            lock.persist_payload(failed_payload)
            if purpose == "transaction":
                self._runtime_lock_payload = failed_payload
            else:
                self._owned_payload = failed_payload
                self._ownership_recovery_pending = True
            self._write_circuit_open = detail
            return {"ok": False, "detail": detail}
        if not lock.clear():
            detail = f"RAPL {purpose} recovered; runtime lock clear failed"
            self._write_circuit_open = detail
            if purpose == "ownership":
                self._ownership_recovery_pending = True
            return {"ok": False, "detail": detail}
        if purpose == "transaction":
            self._runtime_lock_payload = None
        else:
            self._owned_payload = None
            self._owns_state = False
            self._ownership_recovery_pending = False
        self._write_circuit_open = None
        return {"ok": True, "detail": f"RAPL {purpose} recovered"}

    @property
    def safety_locked(self):
        return bool(
            self._runtime_lock_payload is not None
            or self._ownership_recovery_pending
            or self._write_circuit_open is not None
        )

    @property
    def owns_auto_state(self):
        return bool(
            self._owned_payload is not None
            or self._runtime_lock_payload is not None
        )

    @property
    def reselection_safe_after_use(self):
        return self.owns_auto_state

    def ready(self):
        return bool(self.supported and not self.safety_locked)

    def probe(self):
        return self.ready()

    def _constraint(self, i: int) -> str:
        return os.path.join(self._dir or "", f"constraint_{i}_power_limit_uw")

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _read_text(self, path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return None

    def _write(self, path, value) -> bool:
        try:
            with open(path, "w") as f:
                f.write(str(value))
            return True
        except OSError:
            return False

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def auto_level_limits(self):
        maximum = min(self._fallback.max_w, 30)
        return {
            rail: {"min": self._fallback.min_w, "max": maximum}
            for rail in ("pl1", "pl2")
        }

    def auto_physical_levels(self, levels):
        return {
            "pl1": int(levels["pl1"]),
            "pl2": int(levels.get("pl2", levels["pl1"])),
        }

    def _clamp_auto(self, watts):
        maximum = min(self._fallback.max_w, 30)
        return max(self._fallback.min_w, min(int(watts), maximum))

    def apply_auto_targets(self, targets: dict[str, int], ac: bool) -> TdpResult:
        requested = int(targets["pl1"])
        if not self.auto_tdp_safe:
            return TdpResult(requested, None, False, "complete PL1/PL2 RAPL control unavailable")
        if self.safety_locked:
            return TdpResult(requested, self.read_applied(), False, "RAPL recovery pending")

        target_w = {
            "long_term": self._clamp_auto(requested),
            "short_term": self._clamp_auto(targets.get("pl2", requested)),
        }
        snapshot, missing = self._capture_auto_snapshot()
        if missing:
            return TdpResult(
                requested,
                self.read_applied(),
                False,
                "RAPL snapshot unavailable: " + ", ".join(missing),
            )
        if not self._snapshot_valid(snapshot):
            return TdpResult(
                requested,
                self.read_applied(),
                False,
                "RAPL snapshot outside the safe restore envelope",
            )
        first_claim = self._owned_payload is None
        if first_claim:
            owned_payload = {
                "state": "ownership_pending",
                "detail": "RAPL ownership snapshot pending",
                "snapshot": snapshot,
            }
            if not self._ownership_lock.persist_payload(owned_payload):
                return TdpResult(
                    requested,
                    self.read_applied(),
                    False,
                    "RAPL ownership safety lock unavailable; no writes performed",
                )
            self._owned_payload = owned_payload
        transaction_payload = {
            "state": "transaction_pending",
            "detail": "RAPL transaction pending",
            "snapshot": snapshot,
        }
        if not self._safety_lock.persist_payload(transaction_payload):
            if first_claim:
                if self._ownership_lock.clear():
                    self._owned_payload = None
                else:
                    self._ownership_recovery_pending = True
                    self._write_circuit_open = "RAPL ownership lock clear failed"
            return TdpResult(
                requested,
                self.read_applied(),
                False,
                "RAPL transaction safety lock unavailable; no writes performed",
            )
        self._runtime_lock_payload = transaction_payload
        target_snapshot = {
            label: target_w["long_term" if label.endswith("/pl1") else "short_term"]
            * 1_000_000
            for label in snapshot
        }
        confirmed, problems = self._write_and_verify_snapshot(target_snapshot)
        if not confirmed:
            rollback = self._restore_payload("transaction")
            rollback_detail = rollback["detail"]
            if first_claim and not rollback["ok"]:
                self._ownership_recovery_pending = True
            if rollback["ok"] and first_claim:
                if self._ownership_lock.clear():
                    self._owned_payload = None
                else:
                    self._ownership_recovery_pending = True
                    self._write_circuit_open = "RAPL ownership lock clear failed"
                    rollback_detail += "; ownership lock clear failed"
            return TdpResult(
                target_w["long_term"],
                self.read_applied(),
                False,
                "AutoTDP PL1/PL2 write not confirmed: "
                + ", ".join(problems)
                + "; "
                + rollback_detail,
            )
        if not self._safety_lock.clear():
            self._write_circuit_open = "RAPL write confirmed; transaction lock clear failed"
            return TdpResult(
                target_w["long_term"],
                self.read_applied(),
                False,
                self._write_circuit_open,
            )
        self._runtime_lock_payload = None
        self._owns_state = True
        return TdpResult(
            target_w["long_term"],
            self.read_applied(),
            True,
            "",
        )

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "intel-rapl powercap not present")
        if self._owned_payload is not None or self._runtime_lock_payload is not None:
            if not self.release():
                return TdpResult(
                    watts,
                    self.read_applied(),
                    False,
                    "RAPL AutoTDP state could not be restored",
                )
        target = self._fallback.clamp(watts, ac)
        ok = self._write(self._constraint(0), target * 1_000_000)
        applied = self.read_applied()
        # RAPL quantizes the limit to the package power-unit granularity, so the
        # readback can round to target±1 W even on a good write — accept ±1 W.
        success = ok and applied is not None and abs(applied - target) <= 1
        detail = "" if success else f"write not confirmed (wanted {target}, read {applied})"
        return TdpResult(target, applied, success, detail)

    def read_applied(self) -> int | None:
        return self._read_constraint_w(0)

    def _read_constraint_w(self, index):
        value = self._read_int(self._constraint(index))
        return round(value / 1_000_000) if value is not None else None

    def observe(self):
        if not self.supported:
            return TdpObservation(readable=True)
        if self._owns_state:
            surfaces = {}
            for label, paths in self._auto_surfaces.items():
                rails = {}
                for rail, path in paths.items():
                    value = self._read_int(path)
                    if value is not None:
                        rails[rail] = RailReading(
                            round(value / 1_000_000)
                        )
                surface = self.name if label == "mmio" else f"{self.name}:{label}"
                surfaces[surface] = rails
            return TdpObservation(readable=True, surfaces=surfaces)
        rails = {}
        for rail, index in (("pl1", 0), ("pl2", 1)):
            value = self._read_constraint_w(index)
            if value is not None:
                rails[rail] = RailReading(value)
        return TdpObservation(
            readable=True,
            surfaces={self.name: rails} if rails else {},
        )

    def auto_observation_confirmed(self, observation, setpoint, tolerance):
        if self.safety_locked or not self._owns_state:
            return False
        for label in self._auto_paths():
            source, rail = label.split("/", 1)
            surface = self.name if source == "mmio" else f"{self.name}:{source}"
            reading = observation.surfaces.get(surface, {}).get(rail)
            if (
                reading is None
                or reading.applied_w is None
                or abs(int(reading.applied_w) - int(setpoint)) > int(tolerance)
            ):
                return False
        return True

    def recover_runtime_transaction(self):
        if self._runtime_lock_payload is not None:
            recovered = self._restore_payload("transaction")
            if not recovered["ok"]:
                return recovered
        if self._ownership_recovery_pending:
            return self._restore_payload("ownership")
        return {"ok": True, "detail": "no RAPL recovery pending"}

    def release(self):
        if self._runtime_lock_payload is not None:
            recovered = self._restore_payload("transaction")
            if not recovered["ok"]:
                return False
        if self._owned_payload is None:
            return not self._ownership_recovery_pending
        return bool(self._restore_payload("ownership")["ok"])
