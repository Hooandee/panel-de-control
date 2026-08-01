"""Capability-gated virtual controller transitions for resident managers."""
import glob
import os
import time

from controllers import hhd_config


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
