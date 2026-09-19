from tdp.backend import TDPBackend
from tdp.types import TdpObservation, TdpResult


class MsiClawIntelBackend(TDPBackend):
    """Keep MSI firmware manual control and co-own every AutoTDP surface."""

    def __init__(self, manual, auto_firmware, auto_rapl):
        self._manual = manual
        self._auto_firmware = auto_firmware
        self._auto_rapl = auto_rapl
        self.name = manual.name
        self.supported = manual.supported
        self.supports_levels = manual.supports_levels
        self.readback = manual.readback
        self.primary_rail = manual.primary_rail
        self.low_battery_hold_strategy = manual.low_battery_hold_strategy
        self.read_tolerance_w = max(
            int(getattr(auto_firmware, "read_tolerance_w", 0)),
            int(getattr(auto_rapl, "read_tolerance_w", 0)),
        )
        self.auto_tdp_safe = bool(
            auto_firmware.auto_tdp_safe and auto_rapl.auto_tdp_safe
        )

    @property
    def safety_locked(self):
        return bool(
            getattr(self._manual, "safety_locked", False)
            or getattr(self._auto_firmware, "safety_locked", False)
            or getattr(self._auto_rapl, "safety_locked", False)
        )

    @property
    def owns_auto_state(self):
        return bool(
            getattr(self._auto_firmware, "_owned_payload", None)
            or getattr(self._auto_firmware, "_runtime_lock_payload", None)
            or getattr(self._auto_rapl, "owns_auto_state", False)
        )

    @property
    def reselection_safe_after_use(self):
        return self.owns_auto_state

    def selection_ready(self):
        return self._manual.selection_ready()

    def selection_diagnostics(self):
        return self._manual.selection_diagnostics()

    def ready(self):
        return bool(self.supported and not self.safety_locked and self.selection_ready())

    def probe(self):
        return self.ready()

    def get_limits(self):
        return self._manual.get_limits()

    def level_limits(self):
        return self._manual.level_limits()

    def reconciliation_levels(self, levels):
        return self._manual.reconciliation_levels(levels)

    def physical_levels(self, levels):
        return self._manual.physical_levels(levels)

    def auto_level_limits(self):
        firmware = self._auto_firmware.level_limits()
        rapl = self._auto_rapl.auto_level_limits()
        return {
            rail: {
                "min": max(int(firmware[rail]["min"]), int(rapl[rail]["min"])),
                "max": min(int(firmware[rail]["max"]), int(rapl[rail]["max"])),
            }
            for rail in ("pl1", "pl2")
            if rail in firmware and rail in rapl
        }

    def auto_physical_levels(self, levels):
        return {
            "pl1": int(levels["pl1"]),
            "pl2": int(levels.get("pl2", levels["pl1"])),
        }

    def _release_auto_surfaces(self):
        rapl_ok = self._auto_rapl.release()
        firmware_ok = self._auto_firmware.release()
        return bool(rapl_ok and firmware_ok)

    def apply_auto_targets(self, targets, ac):
        requested = int(targets["pl1"])
        if not self.auto_tdp_safe:
            return TdpResult(
                requested,
                self.read_applied(),
                False,
                "complete MSI firmware and RAPL control unavailable",
            )
        if self.safety_locked:
            return TdpResult(
                requested,
                self.read_applied(),
                False,
                "MSI AutoTDP recovery pending",
            )
        physical = self.auto_physical_levels(targets)
        firmware = self._auto_firmware.set_levels(
            physical["pl1"],
            physical["pl2"],
            physical["pl2"],
            ac,
        )
        if not firmware.ok:
            return firmware
        rapl = self._auto_rapl.apply_auto_targets(physical, ac)
        if rapl.ok:
            return TdpResult(requested, firmware.applied_w, True, "")
        restored = self._release_auto_surfaces()
        detail = rapl.detail
        if not restored:
            detail += "; MSI AutoTDP rollback incomplete"
        return TdpResult(requested, self.read_applied(), False, detail)

    def _release_before_manual(self):
        return not self.owns_auto_state or self._release_auto_surfaces()

    def set_tdp(self, watts, ac):
        if not self._release_before_manual():
            return TdpResult(
                int(watts),
                self.read_applied(),
                False,
                "MSI AutoTDP state could not be restored",
            )
        return self._manual.set_tdp(watts, ac)

    def set_levels(self, pl1, pl2, pl3, ac):
        if not self._release_before_manual():
            return TdpResult(
                int(pl1),
                self.read_applied(),
                False,
                "MSI AutoTDP state could not be restored",
            )
        return self._manual.set_levels(pl1, pl2, pl3, ac)

    def apply_targets(self, targets, ac):
        primary = int(targets[self.primary_rail])
        return self.set_levels(
            int(targets.get("pl1", primary)),
            int(targets.get("pl2", primary)),
            int(targets.get("pl3", targets.get("pl2", primary))),
            ac,
        )

    def read_applied(self):
        if self.owns_auto_state:
            return self._auto_firmware.read_applied()
        return self._manual.read_applied()

    def observe(self):
        if not self.owns_auto_state:
            return self._manual.observe()
        firmware = self._auto_firmware.observe()
        rapl = self._auto_rapl.observe()
        return TdpObservation(
            readable=firmware.readable and rapl.readable,
            surfaces={**firmware.surfaces, **rapl.surfaces},
        )

    def auto_observation_confirmed(self, observation, setpoint, tolerance):
        for rail in ("pl1", "pl2"):
            reading = observation.surfaces.get(self.name, {}).get(rail)
            if (
                reading is None
                or reading.applied_w is None
                or abs(int(reading.applied_w) - int(setpoint)) > int(tolerance)
            ):
                return False
        return self._auto_rapl.auto_observation_confirmed(
            observation,
            setpoint,
            tolerance,
        )

    def recover_runtime_transaction(self):
        firmware = self._auto_firmware.recover_runtime_transaction()
        rapl = self._auto_rapl.recover_runtime_transaction()
        ok = bool(firmware.get("ok") and rapl.get("ok"))
        return {
            "ok": ok,
            "detail": "; ".join(
                detail
                for detail in (firmware.get("detail"), rapl.get("detail"))
                if detail
            ),
        }

    def release(self):
        return self._release_auto_surfaces()

    def profile_choices(self):
        return self._manual.profile_choices()

    def read_profile(self):
        return self._manual.read_profile()

    def set_profile(self, mode):
        return self._manual.set_profile(mode)

    def diagnostics(self):
        detail = self._manual.diagnostics()
        detail["auto_surfaces"] = {
            "firmware_pl1_pl2": self._auto_firmware.auto_tdp_safe,
            "rapl_mmio_msr_pl1_pl2": self._auto_rapl.auto_tdp_safe,
            "owned": self.owns_auto_state,
        }
        return detail
