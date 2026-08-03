from dataclasses import dataclass

from cpu.coordinator import CpuCoordinator


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

    def set_window(self, minimum, maximum):
        self.events.append(("frequency", minimum, maximum))
        if not self.fail:
            self.requested = (minimum, maximum)
        return _FrequencyResult(not self.fail, "failed" if self.fail else "applied", "write_failed" if self.fail else None)

    def set_auto(self):
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
