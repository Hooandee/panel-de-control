PRESETS = {
    "silent": (15, 55),
    "balanced": (23, 80),
    "performance": (30, 110),
}

CPU_POLICIES = {
    "silent": "low-power",
    "balanced": "balanced",
    "performance": "performance",
}


class _NoCpuPolicy:
    supported = False

    def state(self):
        return None

    def set(self, mode):
        return {"ok": False, "applied": None}

    def restore(self, target=None):
        return {"ok": True, "applied": None}


class DesktopPowerCoordinator:
    """Atomic owner for separate CPU package and discrete-GPU power limits."""

    def __init__(
        self,
        cpu_backend,
        gpu_cap,
        cpu_policy=None,
        persisted_state=None,
        persist_state=None,
        boot_id=None,
        device_key=None,
    ) -> None:
        self._cpu = cpu_backend
        self._gpu = gpu_cap
        self._cpu_policy = cpu_policy or _NoCpuPolicy()
        self._persist_state = persist_state
        self._boot_id = boot_id or self._read_boot_id()
        self._device_key = device_key
        self._baseline = None
        self._durable_state_reason = None
        self._cpu_owned = False
        self._policy_owned = False
        self._gpu_owned = False
        self._active = False
        self._mode = "free"
        self._load_persisted_state(persisted_state)

    @staticmethod
    def _read_boot_id():
        try:
            with open("/proc/sys/kernel/random/boot_id") as handle:
                value = handle.read().strip()
        except OSError:
            return None
        return value or None

    @staticmethod
    def _valid_positive_int(value):
        return not isinstance(value, bool) and isinstance(value, int) and value > 0

    @classmethod
    def _valid_baseline(cls, baseline):
        if not isinstance(baseline, dict) or set(baseline) != {
            "cpu_w", "cpu_policy", "gpu_uw"
        }:
            return False
        cpu_w = baseline.get("cpu_w")
        policy = baseline.get("cpu_policy")
        gpu_uw = baseline.get("gpu_uw")
        return (
            (cpu_w is None or cls._valid_positive_int(cpu_w))
            and (policy is None or isinstance(policy, str) and bool(policy.strip()))
            and (gpu_uw is None or cls._valid_positive_int(gpu_uw))
            and any(value is not None for value in baseline.values())
        )

    def _payload(self, baseline):
        if baseline is None:
            return None
        return {
            "version": 1,
            "boot_id": self._boot_id,
            "device_key": self._device_key,
            "baseline": dict(baseline),
        }

    def _persist_ownership(self, baseline) -> bool:
        if not callable(self._persist_state):
            return True
        try:
            self._persist_state(self._payload(baseline))
            return True
        except Exception:  # noqa: BLE001
            self._durable_state_reason = "ownership_persist_failed"
            return False

    def _set_baseline(self, baseline) -> None:
        self._baseline = dict(baseline) if baseline is not None else None
        self._cpu_owned = bool(baseline and baseline.get("cpu_w") is not None)
        self._policy_owned = bool(
            baseline and baseline.get("cpu_policy") is not None)
        self._gpu_owned = bool(baseline and baseline.get("gpu_uw") is not None)
        self._active = self._cpu_owned or self._policy_owned or self._gpu_owned

    def _load_persisted_state(self, state) -> None:
        if state is None:
            return
        if (
            not isinstance(state, dict)
            or state.get("version") != 1
            or not self._boot_id
            or state.get("boot_id") != self._boot_id
            or state.get("device_key") != self._device_key
        ):
            self._durable_state_reason = "ownership_state_stale"
            self._persist_ownership(None)
            return
        baseline = state.get("baseline")
        if not self._valid_baseline(baseline):
            self._durable_state_reason = "ownership_state_invalid"
            return
        self._set_baseline(baseline)

    def _capture_baseline(self):
        cpu_w = self._cpu.read_applied() if getattr(self._cpu, "supported", False) else None
        policy = self._cpu_policy.state() if self._cpu_policy.supported else None
        capture_gpu = getattr(self._gpu, "capture", None)
        if self._gpu.supported:
            gpu_uw = capture_gpu() if callable(capture_gpu) else None
        else:
            gpu_uw = None
        baseline = {
            "cpu_w": cpu_w,
            "cpu_policy": policy,
            "gpu_uw": gpu_uw,
        }
        required_missing = (
            getattr(self._cpu, "supported", False) and cpu_w is None
            or self._cpu_policy.supported and policy is None
            or self._gpu.supported and gpu_uw is None
        )
        return None if required_missing or not self._valid_baseline(baseline) else baseline

    def _ownership_surfaces_available(self) -> bool:
        baseline = self._baseline or {}
        return not (
            baseline.get("cpu_w") is not None
            and not getattr(self._cpu, "supported", False)
            or baseline.get("cpu_policy") is not None
            and not self._cpu_policy.supported
            or baseline.get("gpu_uw") is not None
            and not self._gpu.supported
        )

    def _ensure_ownership(self):
        if self._durable_state_reason == "ownership_state_invalid":
            return False, "desktop ownership state invalid"
        if callable(self._persist_state) and (not self._boot_id or not self._device_key):
            return False, "desktop ownership identity unavailable"
        if self._baseline is not None:
            if not self._ownership_surfaces_available():
                return False, "desktop ownership surface unavailable"
            return True, None
        baseline = self._capture_baseline()
        if baseline is None:
            return False, "desktop baseline unavailable"
        if not self._persist_ownership(baseline):
            return False, "desktop ownership persist failed"
        self._set_baseline(baseline)
        self._durable_state_reason = None
        return True, None

    def state(self) -> dict:
        gpu = self._gpu.state()
        return {
            "supported": bool(
                getattr(self._cpu, "supported", False)
                or self._cpu_policy.supported
                or gpu["supported"]
            ),
            "cpu_supported": bool(getattr(self._cpu, "supported", False)),
            "cpu_policy_supported": bool(self._cpu_policy.supported),
            "cpu_policy": self._cpu_policy.state(),
            "gpu_supported": bool(gpu["supported"]),
            "mode": self._mode,
            "cpu_w": self._cpu.read_applied() if getattr(self._cpu, "supported", False) else None,
            "gpu_w": gpu["current_w"],
            "cpu_min_w": 4,
            "cpu_max_w": 30,
            "gpu_min_w": gpu["min_w"],
            "gpu_max_w": gpu["max_w"],
            "presets": {
                key: {
                    "cpu_w": cpu if getattr(self._cpu, "supported", False) else None,
                    "cpu_policy": CPU_POLICIES[key] if self._cpu_policy.supported else None,
                    "gpu_w": gpu_w if gpu["supported"] else None,
                }
                for key, (cpu, gpu_w) in PRESETS.items()
            },
        }

    def apply(self, mode: str) -> dict:
        if mode == "free":
            return self.restore()
        values = PRESETS.get(mode)
        if values is None:
            return {"ok": False, "mode": self._mode, "cpu_w": None, "gpu_w": None,
                    "detail": "unknown desktop power mode"}
        return self._apply_limits(*values, mode=mode)

    def apply_custom(self, cpu_w: int, gpu_w: int) -> dict:
        gpu_state = self._gpu.state()
        cpu_target = max(4, min(30, int(cpu_w)))
        if (gpu_state["supported"]
                and (gpu_state["min_w"] is None or gpu_state["max_w"] is None)):
            return {"ok": False, "mode": self._mode, "cpu_w": None, "gpu_w": None,
                    "detail": "GPU TGP bounds unavailable"}
        gpu_target = (
            max(gpu_state["min_w"], min(gpu_state["max_w"], int(gpu_w)))
            if gpu_state["supported"] else int(gpu_w)
        )
        return self._apply_limits(cpu_target, gpu_target, mode="custom")

    def _apply_limits(self, cpu_w: int, gpu_w: int, mode: str) -> dict:
        cpu_supported = bool(getattr(self._cpu, "supported", False))
        gpu_supported = bool(self._gpu.supported)
        policy_supported = bool(self._cpu_policy.supported and mode in CPU_POLICIES)
        if not cpu_supported and not gpu_supported and not policy_supported:
            return {"ok": False, "mode": self._mode, "cpu_w": None, "gpu_w": None,
                    "detail": "desktop power control unavailable"}
        owned, ownership_detail = self._ensure_ownership()
        if not owned:
            return {"ok": False, "mode": self._mode, "cpu_w": None,
                    "gpu_w": self._gpu.state()["current_w"] if gpu_supported else None,
                    "detail": ownership_detail}
        cpu_result = None
        if cpu_supported:
            self._active = True
            self._mode = mode
            cpu_result = self._cpu.set_tdp(int(cpu_w), True)
            if not cpu_result.ok:
                rollback = self._restore_owned()
                return {"ok": False, "mode": self._mode, "cpu_w": cpu_result.applied_w,
                        "gpu_w": self._gpu.state()["current_w"] if gpu_supported else None,
                        "detail": self._failure_detail(cpu_result.detail, rollback)}
        if policy_supported:
            self._active = True
            self._mode = mode
        policy_result = self._cpu_policy.set(CPU_POLICIES[mode]) if policy_supported else {
            "ok": True, "applied": None}
        if not policy_result.get("ok"):
            rollback = self._restore_owned()
            return {"ok": False, "mode": self._mode,
                    "cpu_w": cpu_result.applied_w if cpu_result is not None else None,
                    "gpu_w": self._gpu.state()["current_w"] if gpu_supported else None,
                    "detail": self._failure_detail(
                        "CPU platform profile readback failed", rollback)}
        if gpu_supported:
            self._active = True
            self._mode = mode
        gpu_result = self._gpu.set_watts(int(gpu_w)) if gpu_supported else {
            "ok": True, "applied_w": None, "detail": "GPU unavailable"}
        if not gpu_result.get("ok"):
            rollback = self._restore_owned()
            return {"ok": False, "mode": self._mode,
                    "cpu_w": self._cpu.read_applied() if cpu_supported else None,
                    "gpu_w": self._gpu.state()["current_w"],
                    "detail": self._failure_detail(
                        gpu_result.get("detail", "GPU apply failed"), rollback)}
        self._active = True
        self._mode = mode
        domains = "applied"
        if not cpu_supported and policy_supported:
            domains = "applied (CPU policy + GPU; CPU watts unavailable)"
        elif not cpu_supported:
            domains = "applied (GPU only; CPU watts unavailable)"
        elif not gpu_supported:
            domains = "applied (CPU only; GPU TGP unavailable)"
        return {"ok": True, "mode": mode,
                "cpu_w": cpu_result.applied_w if cpu_result is not None else None,
                "gpu_w": gpu_result.get("applied_w"), "detail": domains}

    @staticmethod
    def _failure_detail(detail: str, rollback: dict) -> str:
        return detail if rollback["ok"] else f"{detail}; rollback pending"

    def _restore_owned(self) -> dict:
        baseline = self._baseline or {}
        gpu_ok = True
        if self._gpu_owned:
            gpu_result = self._gpu.restore(baseline.get("gpu_uw"))
            gpu_ok = bool(gpu_result.get("ok"))

        policy_ok = True
        if self._policy_owned:
            policy_result = self._cpu_policy.restore(baseline.get("cpu_policy"))
            policy_ok = bool(policy_result.get("ok"))

        cpu_ok = True
        if self._cpu_owned:
            cpu_w = baseline.get("cpu_w")
            cpu_ok = cpu_w is not None and bool(
                self._cpu.set_tdp(int(cpu_w), True).ok)

        hardware_ok = cpu_ok and policy_ok and gpu_ok
        cleared = hardware_ok and self._persist_ownership(None)
        if cleared:
            self._set_baseline(None)
            self._mode = "free"
            self._durable_state_reason = None
        return {"ok": cleared, "cpu_ok": cpu_ok,
                "policy_ok": policy_ok, "gpu_ok": gpu_ok,
                "ownership_ok": cleared if hardware_ok else None}

    def restore(self) -> dict:
        if self._durable_state_reason == "ownership_state_invalid":
            return {"ok": False, "mode": self._mode, "cpu_w": None,
                    "gpu_w": None, "detail": "desktop ownership state invalid"}
        if not self._active:
            self._mode = "free"
            return {"ok": True, "mode": "free", "cpu_w": None,
                    "gpu_w": None, "detail": "already free"}
        result = self._restore_owned()
        return {"ok": result["ok"], "mode": self._mode,
                "cpu_w": self._cpu.read_applied() if self._cpu.supported else None,
                "gpu_w": self._gpu.state()["current_w"],
                "detail": "restored" if result["ok"] else "desktop power restore failed"}
