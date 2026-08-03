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

    def __init__(self, events, fail=False, auto_status="restored"):
        self.events = events
        self.fail = fail
        self.auto_status = auto_status

    def set_window(self, minimum, maximum):
        self.events.append(("frequency", minimum, maximum))
        return _FrequencyResult(not self.fail, "failed" if self.fail else "applied", "write_failed" if self.fail else None)

    def set_auto(self):
        self.events.append(("frequency", "auto"))
        return _FrequencyResult(self.auto_status == "restored", self.auto_status, "baseline_unavailable")

    def diagnostics(self):
        return {"policy_state": []}


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
        ("cores", 4),
        ("smt", False),
        ("boost", False),
        ("frequency", 1_200_000, 2_400_000),
    ]


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
        ("cores", 4),
        ("smt", False),
        ("boost", False),
        ("frequency", 1_200_000, 2_400_000),
        ("boost", True),
        ("smt", True),
        ("cores", 8),
    ]


def test_failed_coordinator_rollback_is_partial():
    events = []
    coordinator = CpuCoordinator(
        _Cores(events, fail_on=8),
        _Toggle("smt", events),
        _Toggle("boost", events),
        _Frequency(events, fail=True),
    )

    result = coordinator.apply(_intent(), generation=4)

    assert result.ok is False
    assert result.status == "partial"
    assert result.rollback == {"attempted": True, "ok": False}


def test_auto_without_session_baseline_is_a_safe_noop():
    events = []
    frequency = _Frequency(events, auto_status="unverifiable")
    coordinator = CpuCoordinator(
        _Cores(events), _Toggle("smt", events), _Toggle("boost", events), frequency
    )

    result = coordinator.apply(_intent(frequency={"manual": False, "min_khz": None, "max_khz": None}), 1)

    assert result.ok is True
    assert result.status == "applied"
    assert events[-1] == ("frequency", "auto")


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
        ("cores", 8),
        ("smt", True),
        ("boost", True),
        ("frequency", "auto"),
    ]
