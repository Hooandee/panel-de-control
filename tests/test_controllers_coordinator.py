import threading

from controllers.coordinator import ControllerCoordinator
from controllers.operations import OperationResult


def _profile(vibration=40):
    return {
        "virtual_controller": {"mode": "xbox_elite"},
        "buttons": {"LeftPaddle1": [{"key": "KeyTab"}]},
        "vibration": {"value": vibration},
    }


class OrderedBackend:
    manager = "inputplumber"

    def __init__(self, mode_status="applied"):
        self.mode_status = mode_status
        self.calls = []
        self.cancelled = []
        self.restored = 0
        self.profile = _profile()

    def apply_component(self, component, desired, appid, generation):
        self.calls.append((component, appid))
        status = self.mode_status if component == "virtual_controller" else "applied"
        return OperationResult(
            component, status, None, self.manager, generation, appid,
            desired, desired if status == "applied" else None,
        )

    def wait_ready(self, appid, generation):
        self.calls.append(("wait_ready", appid))
        return True

    def cancel_transients(self, reason):
        self.cancelled.append(reason)

    def clear_translated_state(self):
        self.calls.append(("clear_translated_state", None))
        return True

    def effective_profile(self, appid):
        return self.profile

    def restore_external(self):
        self.restored += 1
        return True


def test_reconcile_waits_for_mode_before_dependents():
    backend = OrderedBackend()
    coordinator = ControllerCoordinator(backend)

    coordinator.reconcile("42", _profile())

    assert backend.calls == [
        ("virtual_controller", "42"), ("wait_ready", "42"),
        ("buttons", "42"), ("vibration", "42"),
    ]


def test_mode_failure_blocks_dependent_writes():
    backend = OrderedBackend(mode_status="failed")
    snapshot = ControllerCoordinator(backend).reconcile("42", _profile())

    assert backend.calls == [("virtual_controller", "42")]
    assert snapshot["components"]["virtual_controller"]["status"] == "failed"
    assert snapshot["components"]["buttons"]["status"] == "pending"
    assert snapshot["components"]["vibration"]["status"] == "pending"


def test_structured_readiness_recovery_failure_is_not_overwritten():
    class RecoveryBackend(OrderedBackend):
        def wait_ready(self, appid, generation):
            return OperationResult(
                "virtual_controller", "recovery_required",
                "restore_failed", self.manager, generation, appid,
                {"mode": "xbox_elite"},
            )

    backend = RecoveryBackend()
    snapshot = ControllerCoordinator(backend).reconcile("42", _profile())

    assert snapshot["components"]["virtual_controller"] == {
        "status": "recovery_required",
        "owner": "inputplumber",
        "reason": "restore_failed",
        "desired": {"mode": "xbox_elite"},
    }
    assert ("buttons", "42") not in backend.calls
    assert ("vibration", "42") not in backend.calls


def test_new_generation_makes_slow_completion_stale():
    entered = threading.Event()
    release = threading.Event()

    class SlowBackend(OrderedBackend):
        def apply_component(self, component, desired, appid, generation):
            if appid == "10" and component == "virtual_controller":
                entered.set()
                release.wait(timeout=2)
            return super().apply_component(
                component, desired, appid, generation
            )

    backend = SlowBackend()
    coordinator = ControllerCoordinator(backend)
    first = threading.Thread(
        target=lambda: coordinator.reconcile("10", _profile(20))
    )
    first.start()
    assert entered.wait(timeout=1)

    second = threading.Thread(
        target=lambda: coordinator.reconcile("20", _profile(80))
    )
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    snapshot = coordinator.snapshot()
    assert snapshot["appid"] == "20"
    assert snapshot["components"]["vibration"]["desired"] == {"value": 80}
    assert ("buttons", "10") not in backend.calls
    assert ("vibration", "10") not in backend.calls


def test_shutdown_restores_global_then_external_baseline():
    backend = OrderedBackend()
    coordinator = ControllerCoordinator(backend)

    snapshot = coordinator.shutdown(restore_external=True)

    assert backend.cancelled == ["shutdown"]
    assert backend.calls[0] == ("clear_translated_state", None)
    assert ("virtual_controller", None) in backend.calls
    assert backend.restored == 1
    assert snapshot["restore_external"] == "applied"


def test_identical_completed_profile_is_coalesced():
    backend = OrderedBackend()
    coordinator = ControllerCoordinator(backend)

    first = coordinator.reconcile("42", _profile())
    call_count = len(backend.calls)
    second = coordinator.reconcile("42", _profile())

    assert second == first
    assert len(backend.calls) == call_count


def test_failed_component_is_retried_for_identical_profile():
    class FailingOnceBackend(OrderedBackend):
        def __init__(self):
            super().__init__()
            self.failed = False

        def apply_component(self, component, desired, appid, generation):
            result = super().apply_component(
                component, desired, appid, generation
            )
            if component == "vibration" and not self.failed:
                self.failed = True
                return OperationResult(
                    component, "failed", "apply_failed", self.manager,
                    generation, appid, desired,
                )
            return result

    backend = FailingOnceBackend()
    coordinator = ControllerCoordinator(backend)

    first = coordinator.reconcile("42", _profile())
    second = coordinator.reconcile("42", _profile())

    assert first["components"]["vibration"]["status"] == "failed"
    assert second["components"]["vibration"]["status"] == "applied"
    assert backend.calls.count(("vibration", "42")) == 2


def test_failed_external_restore_is_recovery_required_after_cleanup():
    backend = OrderedBackend(mode_status="failed")
    backend.restore_external = lambda: False
    coordinator = ControllerCoordinator(backend)

    snapshot = coordinator.shutdown(restore_external=True)

    assert backend.calls[0] == ("clear_translated_state", None)
    assert snapshot["restore_external"] == "recovery_required"
