from desktop.power import DesktopPowerCoordinator
from tdp.types import TdpResult


class Cpu:
    supported = True
    name = "cpu"

    def __init__(self, applied=30, fail=False):
        self.applied = applied
        self.fail = fail
        self.calls = []
        self.read_calls = 0

    def read_applied(self):
        self.read_calls += 1
        return self.applied

    def set_tdp(self, watts, ac):
        self.calls.append(watts)
        if self.fail:
            return TdpResult(watts, self.applied, False, "cpu failed")
        self.applied = watts
        return TdpResult(watts, watts, True, "")


class Gpu:
    supported = True

    def __init__(self, current=110, fail=False):
        self.current = current
        self.original = None
        self.fail = fail
        self.calls = []

    def state(self):
        return {"supported": True, "current_w": self.current, "min_w": 55,
                "max_w": 110, "default_w": 110}

    def set_watts(self, watts):
        self.calls.append(watts)
        if self.original is None:
            self.original = self.current
        if self.fail:
            return {"ok": False, "applied_w": self.current, "detail": "gpu failed"}
        self.current = watts
        return {"ok": True, "applied_w": watts, "detail": "applied"}

    def capture(self):
        return self.current * 1_000_000

    def restore(self, target=None):
        if target is not None:
            self.current = target // 1_000_000
            self.original = None
        elif self.original is not None:
            self.current = self.original
            self.original = None
        return {"ok": True, "applied_w": self.current, "detail": "restored"}


class UnsupportedGpu(Gpu):
    supported = False

    def state(self):
        return {"supported": False, "current_w": None, "min_w": None,
                "max_w": None, "default_w": None}


class UnsupportedCpu(Cpu):
    supported = False


class Policy:
    supported = True

    def __init__(self):
        self.current = "balanced"
        self.original = None

    def state(self):
        return self.current

    def set(self, mode):
        if self.original is None:
            self.original = self.current
        self.current = mode
        return {"ok": True, "applied": mode}

    def restore(self, target=None):
        if target is not None:
            self.current = target
            self.original = None
        elif self.original is not None:
            self.current = self.original
            self.original = None
        return {"ok": True, "applied": self.current}


class CpuWithFailedFirstRestore(Cpu):
    def __init__(self, applied=30):
        super().__init__(applied=applied)
        self.restore_failures = 1

    def set_tdp(self, watts, ac):
        self.calls.append(watts)
        if len(self.calls) > 1 and self.restore_failures:
            self.restore_failures -= 1
            return TdpResult(watts, self.applied, False, "restore failed")
        self.applied = watts
        return TdpResult(watts, watts, True, "")


def test_free_mode_performs_no_writes_on_fresh_coordinator():
    cpu, gpu = Cpu(), Gpu()
    coordinator = DesktopPowerCoordinator(cpu, gpu)
    result = coordinator.apply("free")
    assert result["ok"] is True
    assert cpu.calls == []
    assert gpu.calls == []
    assert cpu.read_calls == 0


def test_performance_coordinates_cpu_30_and_gpu_110():
    cpu, gpu = Cpu(), Gpu()
    result = DesktopPowerCoordinator(cpu, gpu).apply("performance")
    assert result["ok"] is True
    assert cpu.calls == [30]
    assert gpu.calls == [110]
    assert result["cpu_w"] == 30
    assert result["gpu_w"] == 110


def test_gpu_failure_rolls_cpu_back_to_its_captured_value():
    cpu, gpu = Cpu(applied=27), Gpu(fail=True)
    result = DesktopPowerCoordinator(cpu, gpu).apply("balanced")
    assert result["ok"] is False
    assert cpu.calls == [23, 27]
    assert cpu.applied == 27


def test_failed_apply_keeps_ownership_until_shutdown_restore_succeeds():
    cpu, gpu = CpuWithFailedFirstRestore(applied=27), Gpu(fail=True)
    coordinator = DesktopPowerCoordinator(cpu, gpu)

    assert coordinator.apply("balanced")["ok"] is False
    assert cpu.applied == 23

    restored = coordinator.restore()

    assert restored["ok"] is True
    assert cpu.calls == [23, 27, 27]
    assert cpu.applied == 27
    assert restored["mode"] == "free"


def test_returning_to_free_restores_both_domains():
    cpu, gpu = Cpu(applied=28), Gpu(current=95)
    coordinator = DesktopPowerCoordinator(cpu, gpu)
    assert coordinator.apply("silent")["ok"] is True
    assert coordinator.apply("free")["ok"] is True
    assert cpu.applied == 28
    assert gpu.current == 95


def test_custom_limits_are_clamped_to_validated_desktop_ranges():
    cpu, gpu = Cpu(), Gpu()
    result = DesktopPowerCoordinator(cpu, gpu).apply_custom(100, 5)
    assert result["ok"] is True
    assert cpu.applied == 30
    assert gpu.current == 55


def test_custom_limit_works_on_cpu_only_generic_desktop():
    cpu, gpu = Cpu(), UnsupportedGpu()
    result = DesktopPowerCoordinator(cpu, gpu).apply_custom(19, 80)
    assert result["ok"] is True
    assert result["cpu_w"] == 19
    assert result["gpu_w"] is None
    assert cpu.applied == 19


def test_gpu_only_desktop_profile_is_honest_when_cpu_watts_are_unavailable():
    cpu, gpu = UnsupportedCpu(), Gpu()
    coordinator = DesktopPowerCoordinator(cpu, gpu)
    result = coordinator.apply("balanced")
    assert result["ok"] is True
    assert result["cpu_w"] is None
    assert result["gpu_w"] == 80
    assert cpu.calls == []
    assert "GPU only" in result["detail"]


def test_profiles_coordinate_readback_cpu_policy_with_gpu_tgp():
    cpu, gpu, policy = UnsupportedCpu(), Gpu(), Policy()
    coordinator = DesktopPowerCoordinator(cpu, gpu, cpu_policy=policy)
    result = coordinator.apply("silent")
    assert result["ok"] is True
    assert policy.current == "low-power"
    assert gpu.current == 55
    assert coordinator.restore()["ok"] is True
    assert policy.current == "balanced"
    assert gpu.current == 110


def test_policy_profile_never_advertises_unavailable_cpu_watts():
    state = DesktopPowerCoordinator(UnsupportedCpu(), Gpu(), cpu_policy=Policy()).state()
    assert state["presets"]["silent"] == {
        "cpu_w": None,
        "cpu_policy": "low-power",
        "gpu_w": 55,
    }


def test_policy_only_desktop_is_supported_without_false_gpu_targets():
    state = DesktopPowerCoordinator(
        UnsupportedCpu(), UnsupportedGpu(), cpu_policy=Policy()).state()
    assert state["supported"] is True
    assert state["presets"]["performance"] == {
        "cpu_w": None,
        "cpu_policy": "performance",
        "gpu_w": None,
    }


def test_restart_reuses_durable_baseline_before_reapplying_profile():
    durable = {"value": None}

    def persist(state):
        durable["value"] = state

    cpu, gpu, policy = Cpu(applied=30), Gpu(current=110), Policy()
    first = DesktopPowerCoordinator(
        cpu,
        gpu,
        cpu_policy=policy,
        persisted_state=None,
        persist_state=persist,
        boot_id="boot-1",
        device_key="steam_machine",
    )

    assert first.apply("silent")["ok"] is True
    assert durable["value"]["baseline"] == {
        "cpu_w": 30,
        "cpu_policy": "balanced",
        "gpu_uw": 110_000_000,
    }

    restarted = DesktopPowerCoordinator(
        Cpu(applied=15),
        Gpu(current=55),
        cpu_policy=Policy(),
        persisted_state=durable["value"],
        persist_state=persist,
        boot_id="boot-1",
        device_key="steam_machine",
    )
    restarted._cpu_policy.current = "low-power"

    assert restarted.apply("silent")["ok"] is True
    assert restarted.restore()["ok"] is True
    assert restarted._cpu.applied == 30
    assert restarted._cpu_policy.current == "balanced"
    assert restarted._gpu.current == 110
    assert durable["value"] is None


def test_takeover_never_writes_without_durable_baseline():
    cpu, gpu, policy = Cpu(), Gpu(), Policy()

    def fail_persist(_state):
        raise OSError("disk full")

    coordinator = DesktopPowerCoordinator(
        cpu,
        gpu,
        cpu_policy=policy,
        persist_state=fail_persist,
        boot_id="boot-1",
        device_key="steam_machine",
    )

    result = coordinator.apply("silent")

    assert result["ok"] is False
    assert result["detail"] == "desktop ownership persist failed"
    assert cpu.calls == []
    assert gpu.calls == []
    assert policy.current == "balanced"


def test_new_boot_discards_stale_baseline_and_captures_current_hardware():
    stale = {
        "version": 1,
        "boot_id": "boot-1",
        "device_key": "steam_machine",
        "baseline": {
            "cpu_w": 30,
            "cpu_policy": "balanced",
            "gpu_uw": 110_000_000,
        },
    }
    durable = {"value": stale}

    def persist(state):
        durable["value"] = state

    cpu, gpu, policy = Cpu(applied=28), Gpu(current=95), Policy()
    coordinator = DesktopPowerCoordinator(
        cpu,
        gpu,
        cpu_policy=policy,
        persisted_state=stale,
        persist_state=persist,
        boot_id="boot-2",
        device_key="steam_machine",
    )

    assert durable["value"] is None
    assert coordinator.apply("silent")["ok"] is True
    assert coordinator.restore()["ok"] is True
    assert cpu.applied == 28
    assert gpu.current == 95


def test_failed_ownership_clear_keeps_baseline_for_retry():
    durable = {"value": None, "clear_failures": 1}

    def persist(state):
        if state is None and durable["clear_failures"]:
            durable["clear_failures"] -= 1
            raise OSError("disk full")
        durable["value"] = state

    cpu, gpu = Cpu(applied=30), Gpu(current=110)
    coordinator = DesktopPowerCoordinator(
        cpu,
        gpu,
        persist_state=persist,
        boot_id="boot-1",
        device_key="steam_machine",
    )
    assert coordinator.apply("silent")["ok"] is True

    first = coordinator.restore()

    assert first["ok"] is False
    assert cpu.applied == 30
    assert gpu.current == 110
    assert durable["value"] is not None

    assert coordinator.restore()["ok"] is True
    assert durable["value"] is None


def test_durable_takeover_rejects_missing_boot_identity(monkeypatch):
    cpu, gpu = Cpu(), Gpu()
    monkeypatch.setattr(
        DesktopPowerCoordinator, "_read_boot_id", staticmethod(lambda: None)
    )
    persisted = []
    coordinator = DesktopPowerCoordinator(
        cpu,
        gpu,
        persist_state=persisted.append,
        device_key="steam_machine",
    )

    result = coordinator.apply("balanced")

    assert result["ok"] is False
    assert result["detail"] == "desktop ownership identity unavailable"
    assert persisted == []
    assert cpu.calls == []
    assert gpu.calls == []
