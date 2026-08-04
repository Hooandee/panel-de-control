import copy
import threading

from dataclasses import dataclass

from controllers.operations import OperationResult, OperationState


_MODE_OK = {"applied", "accepted_unverifiable"}


@dataclass(frozen=True)
class ReconcileRequest:
    appid: str | None
    profile: dict
    generation: int
    key: tuple


class ControllerCoordinator:
    def __init__(self, backend):
        self._backend = backend
        self._operations = OperationState()
        self._apply_lock = threading.Lock()
        self._meta_lock = threading.Lock()
        self._last_completed = None

    @staticmethod
    def _key(appid, profile):
        return (
            str(appid) if appid is not None else None,
            copy.deepcopy(profile) if isinstance(profile, dict) else {},
        )

    def _current(self, generation, appid) -> bool:
        return self._operations.is_current(generation, appid)

    def _apply(self, component, desired, appid, generation):
        result = self._backend.apply_component(
            component, desired, appid, generation
        )
        if not isinstance(result, OperationResult):
            return None
        return result if self._operations.publish(result) else None

    def prepare(self, appid, profile, force=False):
        normalized_appid = str(appid) if appid is not None else None
        key = self._key(normalized_appid, profile)
        with self._meta_lock:
            if not force and self._last_completed == key:
                return None
        desired_profile = copy.deepcopy(
            profile if isinstance(profile, dict) else {}
        )
        generation = self._operations.start(
            normalized_appid, desired_profile
        )
        return ReconcileRequest(
            normalized_appid, desired_profile, generation, key
        )

    def execute(self, request: ReconcileRequest) -> dict:
        if not isinstance(request, ReconcileRequest):
            return self.snapshot()
        normalized_appid = request.appid
        desired_profile = request.profile
        generation = request.generation
        with self._apply_lock:
            if not self._current(generation, normalized_appid):
                return self.snapshot()
            mode = self._apply(
                "virtual_controller",
                desired_profile.get("virtual_controller", {}),
                normalized_appid,
                generation,
            )
            if mode is None or mode.status not in _MODE_OK:
                return self.snapshot()
            if not self._current(generation, normalized_appid):
                return self.snapshot()
            readiness = self._backend.wait_ready(
                normalized_appid, generation
            )
            if isinstance(readiness, OperationResult):
                if not self._operations.publish(readiness):
                    return self.snapshot()
                if readiness.status not in _MODE_OK:
                    return self.snapshot()
                readiness = True
            if not readiness:
                self._operations.publish(OperationResult(
                    "virtual_controller", "failed", "device_not_ready",
                    getattr(self._backend, "manager", "none"), generation,
                    normalized_appid,
                    desired_profile.get("virtual_controller", {}),
                ))
                return self.snapshot()

            completed = True
            for component in ("buttons", "vibration"):
                if not self._current(generation, normalized_appid):
                    return self.snapshot()
                result = self._apply(
                    component,
                    desired_profile.get(component, {}),
                    normalized_appid,
                    generation,
                )
                if result is None or result.status not in _MODE_OK:
                    completed = False

            if completed and self._current(generation, normalized_appid):
                with self._meta_lock:
                    self._last_completed = request.key
            return self.snapshot()

    def reconcile(self, appid, profile, force=False) -> dict:
        request = self.prepare(appid, profile, force=force)
        return self.snapshot() if request is None else self.execute(request)

    def cancel_transients(self, reason="cancelled") -> None:
        self.invalidate(reason)
        self._backend.cancel_transients(reason)

    def invalidate(self, reason="cancelled") -> None:
        self._operations.cancel_current(reason)
        with self._meta_lock:
            self._last_completed = None

    def shutdown(self, restore_external=False) -> dict:
        self.cancel_transients("shutdown")
        with self._apply_lock:
            self._backend.clear_translated_state()
        profile = self._backend.effective_profile(None) or {
            "virtual_controller": {}, "buttons": {}, "vibration": {},
        }
        snapshot = self.reconcile(None, profile)
        if restore_external:
            restored = self._backend.restore_external()
            snapshot = {
                **snapshot,
                "restore_external": (
                    "applied" if restored else "recovery_required"
                ),
            }
        return snapshot

    def snapshot(self) -> dict:
        return self._operations.snapshot()
