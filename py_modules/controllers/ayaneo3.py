"""Capability-gated AYANEO 3 Magic Modules actions through HHD ownership."""

import threading
import time


_ACTIONS = {
    "eject_left": ("pop_left", ("left",)),
    "eject_right": ("pop_right", ("right",)),
    "eject_both": ("pop_both", ("left", "right")),
}
_HHD_ROOT = ("magic_modules", "magic_modules")
_CONNECTED_MODULES = frozenset({
    "cross film / joystick",
    "cross / joystick",
    "cross / touchpad",
    "direction / joystick",
    "joystick / cross film",
    "joystick / cross",
    "touchpad / cross",
    "joystick / direction",
    "abxy \\ joystick",
    "abxy \\ touchpad",
    "abxycz",
    "abxy film \\ joystick",
    "joystick \\ abxy",
    "touchpad \\ abxy",
    "abxycz [r]",
    "joystick \\ abxy film",
})
_POLL_DELAY_S = 0.4


def _normalise_module(value) -> str:
    text = str(value or "").strip().casefold()
    if text == "disconnected":
        return "disconnected"
    if text == "ejecting...":
        return "ejecting"
    if text == "activating...":
        return "activating"
    if text == "paused":
        return "paused"
    if text in _CONNECTED_MODULES:
        return "connected"
    return "unknown"


def _result(action, outcome, accepted, modules, reason=None):
    result = {
        "action": action,
        "outcome": outcome,
        "accepted": accepted,
        "modules": modules,
    }
    if reason:
        result["reason"] = reason
    return result


class UnavailableMagicModules:
    source = "hhd"

    def state(self) -> dict:
        return {
            "supported": False,
            "source": self.source,
            "left": "unknown",
            "right": "unknown",
            "busy": False,
        }

    def run(self, action: str) -> dict:
        return _result(
            action,
            "unavailable",
            None,
            self.state(),
            "hhd_magic_modules_absent",
        )


class HhdMagicModules:
    source = "hhd"

    def __init__(
        self,
        read_state,
        post_state,
        sleep=time.sleep,
        monotonic=time.monotonic,
        polls=30,
        deadline_s=12.0,
    ):
        self._read_state = read_state
        self._post_state = post_state
        self._sleep = sleep
        self._monotonic = monotonic
        self._polls = max(1, int(polls))
        self._deadline_s = max(0.1, float(deadline_s))
        self._lock = threading.Lock()

    @staticmethod
    def _tree_from(state):
        try:
            tree = state
            for key in _HHD_ROOT:
                tree = tree[key]
            return tree if isinstance(tree, dict) else None
        except (KeyError, TypeError):
            return None

    def _tree(self):
        try:
            return self._tree_from(self._read_state())
        except Exception:
            return None

    @staticmethod
    def _contract_present(tree) -> bool:
        required = {"pop_left", "pop_right", "pop_both", "info_left", "info_right"}
        return isinstance(tree, dict) and required.issubset(tree)

    def state(self) -> dict:
        tree = self._tree()
        supported = self._contract_present(tree)
        return {
            "supported": supported,
            "source": self.source,
            "left": _normalise_module(tree.get("info_left")) if supported else "unknown",
            "right": _normalise_module(tree.get("info_right")) if supported else "unknown",
            "busy": self._lock.locked(),
        }

    def run(self, action: str) -> dict:
        spec = _ACTIONS.get(action)
        initial = self.state()
        if spec is None or not initial["supported"]:
            return _result(action, "unavailable", None, initial, "hhd_magic_modules_absent")
        if any(initial[target] != "connected" for target in spec[1]):
            return _result(action, "unavailable", None, initial, "module_not_connected")
        if not self._lock.acquire(blocking=False):
            return _result(action, "busy", None, initial, "action_in_progress")
        try:
            deadline = self._monotonic() + self._deadline_s
            payload = {"magic_modules": {"magic_modules": {spec[0]: True}}}
            try:
                echoed = self._post_state(payload)
            except Exception:
                echoed = None
            accepted = (
                True
                if self._contract_present(self._tree_from(echoed))
                else None
            )

            latest = initial
            for _ in range(self._polls):
                if self._monotonic() >= deadline:
                    break
                latest = self.state()
                if all(latest[target] == "disconnected" for target in spec[1]):
                    return _result(action, "confirmed", accepted, latest)
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    break
                self._sleep(min(_POLL_DELAY_S, remaining))
            reason = (
                "disconnect_not_confirmed"
                if accepted is True
                else "hhd_post_unconfirmed"
            )
            return _result(action, "unverifiable", accepted, latest, reason)
        finally:
            self._lock.release()
