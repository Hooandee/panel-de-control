import glob
import os
import threading
import time

from controllers import hhd_config
from controllers import ip_profile


_SAFE_HHD_MODES = ("uinput", "xbox_elite", "hori_steam", "dualsense")
_HHD_IDENTITIES = {
    "uinput": {
        "default": ("045e", "028f", "Handheld Daemon Controller"),
        "steam_input": ("045e", "02e3", "Xbox Elite"),
    },
    "xbox_elite": {
        "default": ("045e", "02e3", "Xbox Elite"),
    },
    "hori_steam": {
        "default": ("0f0d", "0196", "Steam Controller (HHD)"),
    },
    "dualsense": {
        "default": (
            "054c", "0ce6",
            "Sony Interactive Entertainment DualSense Wireless Controller",
        ),
        "steam_input": (
            "054c", "0df2",
            "Sony Interactive Entertainment DualSense Edge Wireless Controller",
        ),
    },
}


def _profile(state):
    key = hhd_config.device_key(state)
    if key is None:
        return None
    controller = state["controllers"].get(key)
    if not isinstance(controller, dict):
        return None
    node = controller.get("controller_mode")
    if not isinstance(node, dict):
        return None
    mode = node.get("mode")
    if not isinstance(mode, str):
        return None
    result = {"mode": mode}
    subtree = node.get(mode)
    paddles = subtree.get("paddles_as") if isinstance(subtree, dict) else None
    if isinstance(paddles, str):
        result["paddles_as"] = paddles
    return result


class HhdVirtualModeAdapter:
    def __init__(
        self,
        store,
        device_key,
        read_state,
        read_settings,
        post_state,
        *,
        sys_root="/sys/class/input",
        sleep=time.sleep,
    ):
        self._store = store
        self._device_key = device_key or ""
        self._read_state = read_state
        self._read_settings = read_settings
        self._post_state = post_state
        self._sys_root = sys_root
        self._sleep = sleep
        self._owner = f"hhd:{self._device_key}"
        self._last_before = None
        read_applied = getattr(self._store, "applied_virtual_mode", None)
        self._last_applied = (
            read_applied(self._owner) or None
            if callable(read_applied) else None
        )

    def _remember_applied(self):
        remember = getattr(self._store, "remember_applied_virtual_mode", None)
        if callable(remember):
            remember(self._owner, self._last_applied or {})

    def capabilities(self, state=None, settings=None):
        state = self._read_state() if state is None else state
        settings = self._read_settings() if settings is None else settings
        modes = (
            hhd_config._mode_schema(
                settings, hhd_config.device_key(state)
            )
            if hhd_config._schema_matches_state(settings, state)
            else None
        )
        current = _profile(state)
        if not isinstance(modes, dict) or current is None:
            return None
        options = [
            mode for mode in _SAFE_HHD_MODES
            if isinstance(modes.get(mode), dict)
        ]
        if not options:
            return None
        return {
            "current": current["mode"],
            "options": ["auto", *options],
            "scope": ["global", "game"],
            "readiness": "evdev_identity",
        }

    def capture_baseline(self):
        current = _profile(self._read_state())
        if current is not None:
            self._store.remember_virtual_mode_baseline(
                self._owner, current
            )
        return self._store.virtual_mode_baseline(self._owner)

    def _post_profile(self, desired):
        state = self._read_state()
        key = hhd_config.device_key(state)
        if key is None:
            return None
        echoed = self._post_state({
            "controllers": {
                key: {"controller_mode": {"mode": desired["mode"]}},
            },
        })
        actual = _profile(echoed)
        if actual is None or actual["mode"] != desired["mode"]:
            return actual
        paddles = desired.get("paddles_as")
        if isinstance(paddles, str):
            echoed = self._post_state({
                "controllers": {
                    key: {
                        "controller_mode": {
                            desired["mode"]: {"paddles_as": paddles},
                        },
                    },
                },
            })
            actual = _profile(echoed)
            if actual != desired:
                return actual
        return actual

    def apply(self, mode):
        capabilities = self.capabilities()
        baseline = self.capture_baseline()
        before = _profile(self._read_state())
        if capabilities is None or before is None or not baseline:
            return {
                "config_confirmed": False,
                "rollback_confirmed": True,
                "actual": before,
                "reason": "capability_unavailable",
            }
        owned = before == baseline or before == self._last_applied
        if not owned:
            return {
                "config_confirmed": False,
                "rollback_confirmed": True,
                "actual": before,
                "reason": "profile_conflict",
            }
        if mode == "auto":
            desired = baseline
        elif mode in capabilities["options"]:
            desired = {"mode": mode}
        else:
            return {
                "config_confirmed": False,
                "rollback_confirmed": True,
                "actual": before,
                "reason": "unsupported_mode",
            }

        actual = self._post_profile(desired)
        confirmed = actual is not None and all(
            actual.get(field) == value for field, value in desired.items()
        )
        if confirmed:
            self._last_before = before
            self._last_applied = None if actual == baseline else actual
            self._remember_applied()
            return {
                "config_confirmed": True,
                "rollback_confirmed": True,
                "actual": actual,
                "reason": None,
            }
        rollback = self._post_profile(before)
        rollback_confirmed = rollback == before
        return {
            "config_confirmed": False,
            "rollback_confirmed": rollback_confirmed,
            "actual": actual,
            "reason": "config_echo_mismatch",
        }

    def rollback_last(self):
        if self._last_before is None:
            return True
        desired = self._last_before
        actual = self._post_profile(desired)
        confirmed = actual == desired
        if confirmed:
            self._last_before = None
            self._last_applied = (
                None
                if desired == self._store.virtual_mode_baseline(self._owner)
                else desired
            )
            self._remember_applied()
        return confirmed

    @staticmethod
    def _identity(mode, paddles):
        choices = _HHD_IDENTITIES.get(mode)
        if choices is None:
            return None
        return choices.get(paddles, choices["default"])

    def _matching_devices(self, identity):
        matches = []
        vendor, product, name = identity
        for event_path in glob.glob(os.path.join(self._sys_root, "event*")):
            device = os.path.join(event_path, "device")
            try:
                with open(os.path.join(device, "id", "vendor")) as f:
                    actual_vendor = f.read().strip().lower()
                with open(os.path.join(device, "id", "product")) as f:
                    actual_product = f.read().strip().lower()
                with open(os.path.join(device, "name")) as f:
                    actual_name = f.read().strip()
            except OSError:
                continue
            if (
                actual_vendor == vendor
                and actual_product == product
                and actual_name == name
            ):
                matches.append(event_path)
        return matches

    def wait_ready(self, mode, timeout=2.0):
        deadline = time.monotonic() + max(0, timeout)
        while True:
            baseline = self._store.virtual_mode_baseline(self._owner)
            expected_mode = baseline.get("mode") if mode == "auto" else mode
            live = _profile(self._read_state()) or {}
            paddles = (
                baseline.get("paddles_as")
                if mode == "auto"
                else live.get("paddles_as")
            )
            identity = self._identity(expected_mode, paddles)
            if identity is not None and len(self._matching_devices(identity)) == 1:
                return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.05)


class InputPlumberVirtualModeAdapter:
    def __init__(self, store, dbus, device_key, *, sleep=time.sleep,
                 monotonic=time.monotonic):
        self._store = store
        self._dbus = dbus
        self._owner = f"inputplumber:{device_key or ''}"
        self._sleep = sleep
        self._monotonic = monotonic
        self._pending = None
        self._transition_generation = 0
        self._transition_lock = threading.Lock()

    @staticmethod
    def _same(left, right):
        return sorted(left or []) == sorted(right or [])

    def _read_targets(self):
        read = getattr(self._dbus, "target_device_types", None)
        return (
            ip_profile.clean_target_devices(read())
            if callable(read)
            else []
        )

    def capabilities(self, current=None):
        read_supported = getattr(
            self._dbus, "supported_target_device_ids", None
        )
        current = self._read_targets() if current is None else current
        if not callable(read_supported) or not current:
            return None
        options = ip_profile.virtual_mode_options(read_supported())
        if len(options) <= 1:
            return None
        return {
            "current": ip_profile.gamepad_target(current),
            "options": options,
            "scope": ["global", "game"],
            "readiness": "dbus_target_type",
        }

    def config(self, appid=None):
        capabilities = self.capabilities()
        desired = self._store.effective_virtual_controller(appid)
        if capabilities is None:
            return {
                "supported": False,
                "mode": desired.get("mode", "auto"),
                "actual_mode": None,
                "options": [],
                "scope": [],
            }
        return {
            "supported": True,
            "mode": desired.get("mode", "auto"),
            "actual_mode": capabilities["current"],
            "options": capabilities["options"],
            "scope": capabilities["scope"],
            "readiness": capabilities["readiness"],
        }

    def _capture_baseline(self, current):
        self._store.remember_virtual_mode_baseline(self._owner, {
            "mode": ip_profile.gamepad_target(current),
            "target_devices": current,
        })
        return self._store.virtual_mode_baseline(self._owner)

    def _owned(self, state, current):
        candidates = [
            state.get("target_devices"),
            state.get("last_applied_target_devices"),
            *(state.get("recovery_target_devices") or []),
        ]
        return any(
            candidate and self._same(current, candidate)
            for candidate in candidates
        )

    def apply(self, mode):
        with self._transition_lock:
            self._transition_generation += 1
            generation = self._transition_generation
            self._pending = None
        current = self._read_targets()
        capabilities = self.capabilities(current)
        set_targets = getattr(self._dbus, "set_target_devices", None)
        if (
            capabilities is None
            or not current
            or mode not in capabilities["options"]
            or not callable(set_targets)
        ):
            return {
                "accepted": False, "ready": False,
                "rollback_confirmed": True,
                "reason": "capability_unavailable",
            }
        state = self._capture_baseline(current)
        if not state or not self._owned(state, current):
            return {
                "accepted": False, "ready": False,
                "rollback_confirmed": True,
                "reason": "profile_conflict",
            }
        baseline = state["target_devices"]
        desired = (
            baseline
            if mode == "auto"
            else ip_profile.replace_gamepad_target(baseline, mode)
        )
        if not desired:
            return {
                "accepted": False, "ready": False,
                "rollback_confirmed": True,
                "reason": "unsupported_mode",
            }
        if self._same(current, desired):
            self._store.remember_applied_virtual_targets(
                self._owner, desired
            )
            return {
                "accepted": True, "ready": True,
                "rollback_confirmed": True,
                "actual": ip_profile.gamepad_target(current),
                "reason": None,
            }
        accepted = bool(set_targets(desired))
        cancelled = False
        if accepted:
            with self._transition_lock:
                if generation == self._transition_generation:
                    self._pending = {
                        "mode": mode,
                        "before": current,
                        "desired": desired,
                        "generation": generation,
                    }
                else:
                    cancelled = True
        if cancelled:
            rollback_confirmed = self._restore(current)
            return {
                "accepted": False, "ready": False,
                "rollback_confirmed": rollback_confirmed,
                "actual": ip_profile.gamepad_target(current),
                "reason": "apply_failed",
            }
        return {
            "accepted": accepted, "ready": False,
            "rollback_confirmed": (
                self._same(self._read_targets(), current)
                if not accepted else True
            ),
            "actual": ip_profile.gamepad_target(current),
            "reason": None if accepted else "apply_failed",
        }

    def _poll(self, expected, timeout=4.0, generation=None):
        deadline = self._monotonic() + max(0.0, float(timeout))
        actual = self._read_targets()
        while not self._same(actual, expected) and self._monotonic() < deadline:
            if (
                generation is not None
                and generation != self._transition_generation
            ):
                break
            self._sleep(0.1)
            actual = self._read_targets()
        return actual

    def _restore(self, targets, timeout=4.0):
        set_targets = getattr(self._dbus, "set_target_devices", None)
        if not callable(set_targets) or not set_targets(targets):
            return self._same(self._read_targets(), targets)
        return self._same(self._poll(targets, timeout), targets)

    def cancel(self):
        with self._transition_lock:
            self._transition_generation += 1
            pending = self._pending
            self._pending = None
        if pending is None:
            return True
        restored = self._restore(pending["before"])
        if restored:
            self._store.remember_applied_virtual_targets(
                self._owner, pending["before"]
            )
        else:
            self._store.remember_virtual_target_recovery(
                self._owner,
                [pending["before"], pending["desired"]],
            )
        return restored

    def wait_ready(self, timeout=4.0):
        with self._transition_lock:
            pending = self._pending
            self._pending = None
        if pending is None:
            actual = self._read_targets()
            return {
                "ready": bool(actual),
                "rollback_confirmed": True,
                "actual": ip_profile.gamepad_target(actual),
            }
        actual = self._poll(
            pending["desired"], timeout, pending["generation"]
        )
        if self._same(actual, pending["desired"]):
            self._store.remember_applied_virtual_targets(
                self._owner, pending["desired"]
            )
            return {
                "ready": True,
                "rollback_confirmed": True,
                "actual": ip_profile.gamepad_target(actual),
            }
        rollback_confirmed = self._restore(pending["before"], timeout)
        if rollback_confirmed:
            self._store.remember_applied_virtual_targets(
                self._owner, pending["before"]
            )
        else:
            self._store.remember_virtual_target_recovery(
                self._owner,
                [pending["before"], pending["desired"]],
            )
        return {
            "ready": False,
            "rollback_confirmed": rollback_confirmed,
            "actual": ip_profile.gamepad_target(actual),
        }

    def restore_external(self, timeout=4.0):
        state = self._store.virtual_mode_baseline(self._owner)
        if not state:
            return True
        baseline = state.get("target_devices")
        current = self._read_targets()
        if not baseline or not self._owned(state, current):
            return False
        if not self._same(current, baseline):
            set_targets = getattr(self._dbus, "set_target_devices", None)
            if not callable(set_targets) or not set_targets(baseline):
                return False
            current = self._poll(baseline, timeout)
        restored = self._same(current, baseline)
        if restored:
            self._store.forget_virtual_mode_baseline(self._owner)
        return restored
