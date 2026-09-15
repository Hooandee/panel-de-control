from dataclasses import dataclass
from pathlib import Path

import pytest

import cpu.controls as controls_module
import cpu.frequency as frequency_module
from cpu.controls import CoreControl, SmtControl, select_boost
from cpu.coordinator import CpuCoordinator
from cpu.frequency import select_cpu_frequency


class _Toggle:
    supported = True

    def __init__(self, name, events, enabled=True, fail_on=None):
        self.name = name
        self.events = events
        self._enabled = enabled
        self.fail_on = fail_on

    def enabled(self):
        return self._enabled

    def set(self, enabled):
        enabled = bool(enabled)
        self.events.append((self.name, enabled))
        if self.fail_on is enabled:
            return False
        self._enabled = enabled
        return True


class _Cores:
    supported = True
    max_cores = 8

    def __init__(self, events, active=8, fail_on=None):
        self.events = events
        self._active = active
        self.fail_on = fail_on

    def active(self):
        return self._active

    def set(self, count):
        count = int(count)
        self.events.append(("cores", count))
        if self.fail_on == count:
            return False
        self._active = count
        return True


@dataclass
class _FrequencyResult:
    ok: bool
    status: str
    reason: str | None = None


class _Frequency:
    supported = True

    def __init__(
        self, events, fail=False, auto_status="restored", requested=None,
        auto_reason="baseline_unavailable",
    ):
        self.events = events
        self.fail = fail
        self.auto_status = auto_status
        self.auto_reason = auto_reason
        self.requested = requested
        self.preserve_calls = []

    def set_window(self, minimum, maximum):
        self.events.append(("frequency", minimum, maximum))
        if not self.fail:
            self.requested = (minimum, maximum)
        return _FrequencyResult(not self.fail, "failed" if self.fail else "applied", "write_failed" if self.fail else None)

    def set_auto(self, preserve_ownership=False):
        self.preserve_calls.append(bool(preserve_ownership))
        self.events.append(("frequency", "auto"))
        ok = self.auto_status == "restored"
        if ok:
            self.requested = None
        return _FrequencyResult(ok, self.auto_status, self.auto_reason)

    def diagnostics(self):
        return {
            "policy_state": [],
            "requested": list(self.requested) if self.requested else None,
        }


class _FrequencyRequiresFullTopology(_Frequency):
    def __init__(self, events, cores, smt, **kwargs):
        super().__init__(events, **kwargs)
        self.cores = cores
        self.smt = smt

    def set_window(self, minimum, maximum):
        if self.cores.active() != self.cores.max_cores or not self.smt.enabled():
            self.events.append(("frequency", "topology_incomplete"))
            return _FrequencyResult(False, "unsupported", "incomplete_policy")
        return super().set_window(minimum, maximum)


class _FailFinalCoreLimitOnce(_Cores):
    def __init__(self, events, active, final_target):
        super().__init__(events, active=active)
        self.final_target = final_target
        self.failed = False

    def set(self, count):
        count = int(count)
        if count == self.final_target and self._active == self.max_cores and not self.failed:
            self.events.append(("cores", count))
            self.failed = True
            return False
        return super().set(count)


class _PartialCoreOnlineFailure(_Cores):
    def set(self, count):
        count = int(count)
        self.events.append(("cores", count))
        if count == self.max_cores:
            self._active = self.max_cores - 2
            return False
        self._active = count
        return True


def _intent(**updates):
    value = {
        "cores": 4,
        "smt": False,
        "boost": False,
        "frequency": {"manual": True, "min_khz": 1_200_000, "max_khz": 2_400_000},
    }
    value.update(updates)
    return value


def test_applies_complete_cpu_transaction_in_fixed_order():
    events = []
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events), _Toggle("boost", events), _Frequency(events)
    )

    result = coordinator.apply(_intent(), generation=7)

    assert result.ok is True
    assert result.generation == 7
    assert events == [
        ("boost", False),
        ("frequency", 1_200_000, 2_400_000),
        ("smt", False),
        ("cores", 4),
    ]


def test_frequency_opens_full_topology_then_restores_requested_cpu_shape():
    events = []
    cores = _Cores(events, active=4)
    smt = _Toggle("smt", events, enabled=False)
    frequency = _FrequencyRequiresFullTopology(events, cores, smt)
    coordinator = CpuCoordinator(cores, smt, _Toggle("boost", events), frequency)

    result = coordinator.apply(_intent(), generation=8)

    assert result.ok is True
    assert cores.active() == 4
    assert smt.enabled() is False
    assert frequency.requested == (1_200_000, 2_400_000)
    assert ("frequency", "topology_incomplete") not in events


def test_final_core_failure_restores_previous_frequency_and_cpu_shape():
    events = []
    cores = _FailFinalCoreLimitOnce(events, active=4, final_target=4)
    smt = _Toggle("smt", events, enabled=True)
    frequency = _Frequency(events, requested=(600_000, 3_000_000))
    coordinator = CpuCoordinator(cores, smt, _Toggle("boost", events), frequency)

    result = coordinator.apply(_intent(), generation=10)

    assert result.ok is False
    assert result.error_code == "cores_write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert cores.active() == 4
    assert smt.enabled() is True
    assert frequency.requested == (600_000, 3_000_000)


def test_partial_core_online_failure_rolls_back_changed_topology():
    events = []
    cores = _PartialCoreOnlineFailure(events, active=4)
    coordinator = CpuCoordinator(
        cores, _Toggle("smt", events), _Toggle("boost", events),
        _Frequency(events),
    )

    result = coordinator.apply(_intent(), generation=11)

    assert result.ok is False
    assert result.error_code == "cores_online_write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert cores.active() == 4


def test_frequency_failure_rolls_back_every_prior_cpu_control():
    events = []
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events), _Toggle("boost", events), _Frequency(events, fail=True)
    )

    result = coordinator.apply(_intent(), generation=3)

    assert result.ok is False
    assert result.status == "failed"
    assert result.error_code == "frequency_write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert events == [
        ("boost", False),
        ("frequency", 1_200_000, 2_400_000),
        ("boost", True),
    ]


def test_failed_coordinator_rollback_is_partial():
    events = []
    coordinator = CpuCoordinator(
        _Cores(events, fail_on=8),
        _Toggle("smt", events, enabled=False, fail_on=False),
        _Toggle("boost", events),
        _Frequency(events, fail=True),
    )

    result = coordinator.apply(_intent(), generation=4)

    assert result.ok is False
    assert result.status == "partial"
    assert result.rollback == {"attempted": True, "ok": False}
    assert result.error_code == "frequency_write_failed"


def test_auto_without_session_baseline_is_a_safe_noop():
    events = []
    frequency = _Frequency(events, auto_status="unverifiable")
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events), _Toggle("boost", events), frequency
    )

    result = coordinator.apply(_intent(frequency={"manual": False, "min_khz": None, "max_khz": None}), 1)

    assert result.ok is True
    assert result.status == "applied"
    assert ("frequency", "auto") in events
    assert events[-2:] == [("smt", False), ("cores", 4)]


def test_auto_with_stale_owned_baseline_is_not_reported_as_success():
    events = []
    frequency = _Frequency(
        events, auto_status="unverifiable", requested=(1_200_000, 2_400_000),
        auto_reason="baseline_stale",
    )
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events), _Toggle("boost", events),
        frequency,
    )

    result = coordinator.apply(
        _intent(frequency={"manual": False, "min_khz": None, "max_khz": None}),
        generation=12,
    )

    assert result.ok is False
    assert result.error_code == "frequency_baseline_stale"
    assert frequency.requested == (1_200_000, 2_400_000)


def test_disabled_system_releases_all_owned_cpu_controls():
    events = []
    coordinator = CpuCoordinator(
        _Cores(events, active=4),
        _Toggle("smt", events, enabled=False),
        _Toggle("boost", events, enabled=False),
        _Frequency(events),
    )

    result = coordinator.apply(_intent(), generation=9, enabled=False)

    assert result.ok is True
    assert events == [
        ("smt", True),
        ("cores", 8),
        ("boost", True),
        ("frequency", "auto"),
    ]


def test_emergency_release_preserves_frequency_ownership():
    events = []
    frequency = _Frequency(events, requested=(1_200_000, 2_400_000))
    coordinator = CpuCoordinator(
        _Cores(events, active=4),
        _Toggle("smt", events, enabled=False),
        _Toggle("boost", events, enabled=False),
        frequency,
    )

    result = coordinator.apply(
        _intent(), generation=9, enabled=False,
        preserve_frequency_ownership=True,
    )

    assert result.ok is True
    assert frequency.preserve_calls == [True]


def test_partial_frequency_handoff_never_restricts_released_cpu_controls():
    events = []
    cores = _Cores(events, active=4)
    smt = _Toggle("smt", events, enabled=False)
    boost = _Toggle("boost", events, enabled=False)
    frequency = _Frequency(
        events,
        auto_status="partial",
        auto_reason="baseline_stale",
        requested=(1_200_000, 2_400_000),
    )
    coordinator = CpuCoordinator(cores, smt, boost, frequency)

    result = coordinator.apply(_intent(), generation=10, enabled=False)

    assert result.ok is False
    assert result.status == "partial"
    assert result.frequency_status == "partial"
    assert cores.active() == 8
    assert smt.enabled() is True
    assert boost.enabled() is True


@pytest.mark.parametrize("failing", ["smt", "cores", "boost"])
def test_failed_handoff_domain_does_not_rollback_or_skip_other_releases(failing):
    events = []
    cores = _Cores(events, active=4, fail_on=8 if failing == "cores" else None)
    smt = _Toggle(
        "smt", events, enabled=False,
        fail_on=True if failing == "smt" else None,
    )
    boost = _Toggle(
        "boost", events, enabled=False,
        fail_on=True if failing == "boost" else None,
    )
    frequency = _Frequency(events)
    coordinator = CpuCoordinator(cores, smt, boost, frequency)

    result = coordinator.apply(_intent(), generation=13, enabled=False)

    assert result.ok is False
    assert result.status == "partial"
    assert result.error_code == f"{failing}_write_failed"
    assert ("frequency", "auto") in events
    if failing != "smt":
        assert smt.enabled() is True
    if failing != "cores":
        assert cores.active() == 8
    if failing != "boost":
        assert boost.enabled() is True


def _amd_boost_kernel(
    tmp_path, monkeypatch, maximum=3_501_250, nominal=2_801_000, baseline_max=None
):
    cpu = tmp_path / "sys/devices/system/cpu"
    boost_path = cpu / "cpufreq/boost"

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value))

    write(boost_path, 1)
    write(cpu / "smt/control", "on")
    policies = []
    for index in range(8):
        write(cpu / f"cpu{index}/topology/core_id", index // 2)
        if index:
            write(cpu / f"cpu{index}/online", 1)
        policy = cpu / f"cpufreq/policy{index}"
        policies.append(policy)
        for name, value in {
            "scaling_driver": "amd-pstate-epp",
            "related_cpus": index,
            "affected_cpus": index,
            "cpuinfo_min_freq": 400_000,
            "cpuinfo_max_freq": maximum,
            "scaling_min_freq": 400_000,
            "scaling_max_freq": baseline_max if baseline_max is not None else maximum,
        }.items():
            write(policy / name, value)

    real_write = controls_module.write_str

    def kernel_write(path, value):
        path = Path(path)
        value = int(value) if path.name != "control" else value
        if path.name in ("scaling_min_freq", "scaling_max_freq"):
            hardware_max = int((path.parent / "cpuinfo_max_freq").read_text())
            minimum = int((path.parent / "scaling_min_freq").read_text())
            maximum_now = int((path.parent / "scaling_max_freq").read_text())
            if not 400_000 <= value <= hardware_max:
                return False
            if path.name == "scaling_min_freq" and value > maximum_now:
                return False
            if path.name == "scaling_max_freq" and value < minimum:
                return False
        ok = real_write(str(path), value)
        if ok and path == boost_path:
            # amd-pstate changes these bounds on boost; observed on Jupiter.
            limit = maximum if value else nominal
            for policy in policies:
                write(policy / "cpuinfo_max_freq", limit)
                write(policy / "scaling_max_freq", limit)
                minimum = int((policy / "scaling_min_freq").read_text())
                write(policy / "scaling_min_freq", min(minimum, limit))
        return ok

    monkeypatch.setattr(controls_module, "write_str", kernel_write)
    monkeypatch.setattr(frequency_module, "write_str", kernel_write)
    durable = {"state": None}

    def persist(state):
        durable["state"] = state

    frequency = select_cpu_frequency(
        root=str(tmp_path), persist_state=persist, boot_id="boot-1"
    )
    boost = select_boost(root=str(tmp_path))
    coordinator = CpuCoordinator(
        CoreControl(root=str(tmp_path)), SmtControl(root=str(tmp_path)),
        boost, frequency,
    )
    return coordinator, frequency, boost, durable, persist


@pytest.mark.parametrize("maximum,nominal", [
    (3_501_250, 2_801_000), (5_134_889, 3_301_000),
])
def test_amd_boost_round_trip_preserves_manual_intent_and_original_baseline(
    tmp_path, monkeypatch, maximum, nominal
):
    coordinator, frequency, boost, durable, _persist = _amd_boost_kernel(
        tmp_path, monkeypatch, maximum, nominal
    )
    intent = _intent(
        smt=True, boost=True,
        frequency={"manual": True, "min_khz": 800_000, "max_khz": maximum},
    )
    assert coordinator.apply(intent, 1).ok is True
    baseline = durable["state"]["baseline"]

    intent["boost"] = False
    disabled = coordinator.apply(intent, 2)

    assert disabled.ok is True
    assert disabled.status == "clamped"
    assert boost.enabled() is False
    assert frequency.get_window() == (800_000, nominal)
    assert frequency.diagnostics()["requested"] == [800_000, maximum]
    assert durable["state"]["baseline"] == baseline

    intent["boost"] = True
    assert coordinator.apply(intent, 3).ok is True
    assert frequency.get_window() == (800_000, maximum)
    assert coordinator.apply(intent, 4, enabled=False).ok is True
    assert frequency.get_window() == (400_000, maximum)
    assert durable["state"] is None


def test_amd_auto_under_boost_limit_keeps_baseline_through_restart_and_handoff(
    tmp_path, monkeypatch
):
    coordinator, frequency, boost, durable, persist = _amd_boost_kernel(
        tmp_path, monkeypatch
    )
    intent = _intent(smt=True, boost=True)
    assert coordinator.apply(intent, 1).ok is True
    baseline = durable["state"]["baseline"]
    intent["boost"] = False
    assert coordinator.apply(intent, 2).ok is True
    intent["frequency"] = {"manual": False}

    restored = coordinator.apply(intent, 3)

    assert restored.ok is True
    assert restored.status == "clamped"
    assert boost.enabled() is False
    assert frequency.get_window() == (400_000, 2_801_000)
    assert frequency.diagnostics()["owned"] is True
    assert durable["state"]["baseline"] == baseline
    assert durable["state"]["version"] == 1
    assert durable["state"]["requested"] == [400_000, 3_501_250]
    assert durable["state"]["restore_pending"] is True

    restarted = select_cpu_frequency(
        root=str(tmp_path), persisted_state=durable["state"],
        persist_state=persist, boot_id="boot-1",
    )
    assert restarted.diagnostics()["owned"] is True
    assert restarted.diagnostics()["requested"] is None
    assert boost.set(True) is True
    assert restarted.set_auto().ok is True
    assert restarted.get_window() == (400_000, 3_501_250)
    assert durable["state"] is None


def test_amd_frequency_failure_after_boost_restores_previous_manual_window(
    tmp_path, monkeypatch
):
    coordinator, frequency, boost, _durable, _persist = _amd_boost_kernel(
        tmp_path, monkeypatch
    )
    intent = _intent(
        smt=True, boost=True,
        frequency={"manual": True, "min_khz": 800_000, "max_khz": 3_000_000},
    )
    assert coordinator.apply(intent, 1).ok is True
    kernel_write = frequency_module.write_str
    failed = False

    def fail_first_frequency_write(path, value):
        nonlocal failed
        if not failed:
            failed = True
            return False
        return kernel_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", fail_first_frequency_write)
    intent["boost"] = False

    result = coordinator.apply(intent, 2)

    assert result.ok is False
    assert result.error_code == "frequency_write_failed"
    assert result.rollback["ok"] is True
    assert boost.enabled() is True
    assert frequency.get_window() == (800_000, 3_000_000)
    assert frequency.diagnostics()["last_failure"]["reason"] == "write_failed"


def test_handoff_keeps_marker_when_boost_readback_does_not_reopen_maximum(
    tmp_path, monkeypatch
):
    coordinator, frequency, boost, durable, _persist = _amd_boost_kernel(
        tmp_path, monkeypatch
    )
    intent = _intent(smt=True, boost=True)
    assert coordinator.apply(intent, 1).ok is True
    intent["boost"] = False
    assert coordinator.apply(intent, 2).ok is True
    kernel_write = controls_module.write_str

    def delayed_maximum(path, value):
        if path.endswith("cpufreq/boost") and int(value) == 1:
            Path(path).write_text("1")
            return True
        return kernel_write(path, value)

    monkeypatch.setattr(controls_module, "write_str", delayed_maximum)
    result = coordinator.apply(intent, 3, enabled=False)

    assert result.ok is False
    assert result.status == "partial"
    assert result.error_code == "frequency_baseline_clamped"
    assert boost.enabled() is True
    assert frequency.get_window() == (400_000, 2_801_000)
    assert durable["state"] is not None
    assert durable["state"]["restore_pending"] is True


def test_failed_core_change_after_auto_release_recovers_pending_baseline(
    tmp_path, monkeypatch
):
    coordinator, frequency, boost, durable, _persist = _amd_boost_kernel(
        tmp_path, monkeypatch, baseline_max=3_200_000
    )
    intent = _intent(smt=True, boost=True)
    assert coordinator.apply(intent, 1).ok is True
    intent["boost"] = False
    intent["frequency"] = {"manual": False}
    assert coordinator.apply(intent, 2).ok is True
    baseline = durable["state"]["baseline"]
    kernel_write = controls_module.write_str

    def refuse_core_offline(path, value):
        if path.endswith("cpu4/online") and int(value) == 0:
            return False
        return kernel_write(path, value)

    monkeypatch.setattr(controls_module, "write_str", refuse_core_offline)
    intent["boost"] = True
    intent["cores"] = 2

    result = coordinator.apply(intent, 3)

    assert result.ok is False
    assert result.error_code == "cores_write_failed"
    assert result.rollback["ok"] is True
    assert boost.enabled() is False
    assert frequency.get_window() == (400_000, 2_801_000)
    assert frequency.diagnostics()["requested"] is None
    assert durable["state"]["baseline"] == baseline
    assert durable["state"]["restore_pending"] is True
    assert coordinator.apply(intent, 4, enabled=False).ok is True
    assert frequency.get_window() == (400_000, 3_200_000)
    assert durable["state"] is None


def test_boost_rollback_does_not_replace_invalid_durable_baseline(tmp_path, monkeypatch):
    coordinator, _frequency, boost, durable, persist = _amd_boost_kernel(
        tmp_path, monkeypatch
    )
    invalid = {
        "version": 1, "boot_id": "boot-1", "baseline": [],
        "requested": [800_000, 2_400_000],
    }
    durable["state"] = invalid
    frequency = select_cpu_frequency(
        root=str(tmp_path), persisted_state=invalid,
        persist_state=persist, boot_id="boot-1",
    )
    coordinator._frequency = frequency
    intent = _intent(smt=True, boost=False)

    result = coordinator.apply(intent, 1)

    assert result.ok is False
    assert result.error_code == "frequency_ownership_state_invalid"
    assert boost.enabled() is True
    assert durable["state"] == invalid
    assert frequency.diagnostics()["durable_state_reason"] == "ownership_state_invalid"
    assert coordinator.apply(intent, 2).error_code == "frequency_ownership_state_invalid"


def _static_frequency(tmp_path, driver):
    policy = tmp_path / "sys/devices/system/cpu/cpufreq/policy0"
    policy.mkdir(parents=True)
    for name, value in {
        "scaling_driver": driver,
        "related_cpus": "0-7",
        "affected_cpus": "0-7",
        "cpuinfo_min_freq": 400_000,
        "cpuinfo_max_freq": 3_500_000,
        "scaling_min_freq": 600_000,
        "scaling_max_freq": 3_000_000,
    }.items():
        (policy / name).write_text(str(value))
    persisted = []
    frequency = select_cpu_frequency(
        root=str(tmp_path), persist_state=persisted.append, boot_id="boot-1"
    )
    return frequency, persisted


@pytest.mark.parametrize("driver", ["intel_pstate", "acpi-cpufreq"])
def test_non_amd_boost_failure_does_not_capture_or_create_ownership(
    tmp_path, monkeypatch, driver
):
    frequency, persisted = _static_frequency(tmp_path, driver)
    events = []
    checkpoint = frequency.checkpoint

    def capture_checkpoint():
        events.append(("checkpoint",))
        return checkpoint()

    monkeypatch.setattr(frequency, "checkpoint", capture_checkpoint)
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events),
        _Toggle("boost", events, fail_on=False), frequency,
    )

    result = coordinator.apply(_intent(cores=8, smt=True), 1)

    assert result.error_code == "boost_write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert events == [("boost", False), ("boost", True)]
    assert persisted == []
    assert frequency.diagnostics()["owned"] is False
    assert frequency.get_window() == (600_000, 3_000_000)


@pytest.mark.parametrize("driver", ["intel_pstate", "acpi-cpufreq"])
def test_non_amd_rollback_keeps_frequency_before_boost(tmp_path, monkeypatch, driver):
    frequency, persisted = _static_frequency(tmp_path, driver)
    events = []
    set_window = frequency.set_window
    set_auto = frequency.set_auto

    def manual(minimum, maximum):
        events.append(("frequency", "manual"))
        return set_window(minimum, maximum)

    def auto():
        events.append(("frequency", "auto"))
        return set_auto()

    monkeypatch.setattr(frequency, "set_window", manual)
    monkeypatch.setattr(frequency, "set_auto", auto)
    coordinator = CpuCoordinator(
        _Cores(events, fail_on=4), _Toggle("smt", events),
        _Toggle("boost", events), frequency,
    )

    result = coordinator.apply(_intent(smt=True), 1)

    assert result.error_code == "cores_write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert events == [
        ("boost", False), ("frequency", "manual"), ("cores", 4),
        ("frequency", "auto"), ("boost", True), ("cores", 8),
    ]
    assert persisted[-1] is None
    assert frequency.get_window() == (600_000, 3_000_000)
