"""Generation-safe, redacted state for controller component operations."""
import copy
import math
import re
import threading

from dataclasses import dataclass

from controllers import ip_profile


COMPONENTS = {"virtual_controller", "buttons", "vibration"}
STATUSES = {
    "applied", "accepted_unverifiable", "pending", "unsupported",
    "conflict", "failed", "recovery_required", "cancelled",
}
REASONS = {
    "apply_failed", "cancelled", "device_not_ready", "identity_changed",
    "invalid_state", "mode_failed", "owner_changed", "profile_conflict",
    "readback_mismatch", "restore_failed", "resume", "shutdown", "superseded",
    "unsupported",
}
OWNERS = {"hhd", "inputplumber", "native", "evdev", "none"}
_MODE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


@dataclass(frozen=True)
class OperationResult:
    component: str
    status: str
    reason: str | None
    owner: str
    generation: int
    appid: str | None
    desired: dict
    actual: dict | None = None


def _button_action(value) -> list:
    return ip_profile.sanitize_button_action(value)


def _component_state(component: str, value) -> dict:
    if not isinstance(value, dict):
        return {}
    if component == "buttons":
        clean = {}
        for source, action in value.items():
            target = _button_action(action)
            if isinstance(source, str) and source and target:
                clean[source] = target
        return clean
    if component == "vibration":
        clean = {}
        if isinstance(value.get("enabled"), bool):
            clean["enabled"] = value["enabled"]
        for field in ("value", "left", "right"):
            number = value.get(field)
            if (
                isinstance(number, (int, float))
                and not isinstance(number, bool)
                and math.isfinite(number)
                and 0 <= number <= 100
            ):
                clean[field] = number
        return clean
    if component == "virtual_controller":
        mode = value.get("mode")
        if isinstance(mode, str) and _MODE.fullmatch(mode):
            return {"mode": mode}
    return {}


class OperationState:
    def __init__(self):
        self._lock = threading.Lock()
        self._generation = 0
        self._appid = None
        self._components = {}

    def start(self, appid, profile) -> int:
        with self._lock:
            self._generation += 1
            self._appid = str(appid) if appid is not None else None
            self._components = {}
            if isinstance(profile, dict):
                for component in COMPONENTS:
                    if component not in profile:
                        continue
                    self._components[component] = {
                        "status": "pending",
                        "desired": _component_state(
                            component, profile.get(component)
                        ),
                    }
            return self._generation

    def publish(self, result: OperationResult) -> bool:
        with self._lock:
            if (
                not isinstance(result, OperationResult)
                or result.generation != self._generation
                or result.appid != self._appid
                or result.component not in COMPONENTS
                or result.status not in STATUSES
                or result.owner not in OWNERS
                or (
                    result.reason is not None
                    and result.reason not in REASONS
                )
            ):
                return False
            clean = {
                "status": result.status,
                "owner": result.owner,
                "desired": _component_state(
                    result.component, result.desired
                ),
            }
            if result.reason is not None:
                clean["reason"] = result.reason
            if result.actual is not None:
                clean["actual"] = _component_state(
                    result.component, result.actual
                )
            self._components[result.component] = clean
            return True

    def is_current(self, generation: int, appid) -> bool:
        normalized_appid = str(appid) if appid is not None else None
        with self._lock:
            return (
                generation == self._generation
                and normalized_appid == self._appid
            )

    def cancel_current(self, reason="cancelled") -> int:
        if reason not in REASONS:
            reason = "cancelled"
        with self._lock:
            self._generation += 1
            for value in self._components.values():
                if value.get("status") == "pending":
                    value["status"] = "cancelled"
                    value["reason"] = reason
            return self._generation

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy({
                "generation": self._generation,
                "appid": self._appid,
                "components": self._components,
            })
