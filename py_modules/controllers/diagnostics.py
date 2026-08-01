"""Read-only, redacted diagnostics for the selected integrated controller."""

import re

from controllers.capabilities import clean_report
from controllers import ip_profile


_OPERATIONS = {
    "discover_composite", "validate_composite", "read_capabilities",
    "read_source_device_paths", "read_profile", "load_profile",
    "reset_default", "read_force_feedback", "set_force_feedback", "rumble",
    "stop_rumble", "apply_profile", "read_supported_target_device_ids",
    "read_target_devices", "read_target_device_types", "set_target_devices",
}
_OWNERS = {"hhd", "inputplumber", "native", "evdev"}
_MODES = {"dual", "gain"}
_REASONS = {
    "busctl_exit", "composite_ambiguous", "composite_not_found",
    "config_echo_mismatch", "identity_changed", "identity_unavailable",
    "initial_readback_unavailable", "invalid_response", "invalid_value",
    "load_failed", "merge_failed", "process_unavailable", "profile_conflict",
    "profile_unavailable", "readback_mismatch", "short_write", "unsupported",
    "write_failed", "target_devices_empty", "target_identity_invalid",
    "target_identity_unavailable",
}
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+()'-]{0,63}")


def _label(value):
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else None


def _number(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return (
        value
        if isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
        else None
    )


def _operation(value):
    if not isinstance(value, dict):
        return None
    clean = {}
    enums = {
        "operation": _OPERATIONS,
        "owner": _OWNERS,
        "mode": _MODES,
        "reason": _REASONS,
    }
    for key, allowed in enums.items():
        if key in value:
            if not isinstance(value[key], str) or value[key] not in allowed:
                return None
            clean[key] = value[key]
    for key in ("ok", "enabled", "rollback_confirmed", "readback"):
        if isinstance(value.get(key), bool):
            clean[key] = value[key]
    for key in ("strength", "profile_bytes", "echoed_value"):
        number = _number(value.get(key))
        if number is not None:
            clean[key] = number
    return clean or None


class IntegratedDiagnostics:
    def __init__(self, root="/"):
        self._root = root

    @staticmethod
    def empty(device_key=None):
        return {
            "device_key": device_key if isinstance(device_key, str) else None,
            "sources": [],
            "batteries": [],
            "inputs": {},
            "motion": None,
            "virtual_controller": None,
            "vibration": None,
            "last_operations": {},
        }

    def snapshot(self, device_key, manager_state) -> dict:
        result = self.empty(device_key)
        if not isinstance(manager_state, dict):
            return result

        manager = manager_state.get("manager")
        version = manager_state.get("manager_version")
        if manager in {"hhd", "inputplumber"}:
            source = {"manager": manager}
            if _label(version) is not None:
                source["version"] = version
            dbus = manager_state.get("dbus")
            if isinstance(dbus, dict):
                name = dbus.get("composite_name")
                count = dbus.get("source_device_count")
                expected_names = ip_profile.composite_names_for(device_key)
                if name in expected_names:
                    source["name"] = name
                    if (
                        isinstance(count, int)
                        and not isinstance(count, bool)
                        and 0 <= count <= 64
                    ):
                        source["source_count"] = count
            result["sources"].append(source)

        capabilities = clean_report(manager_state.get("capabilities"))
        surfaces = capabilities["surfaces"]
        buttons = surfaces.get("buttons")
        if isinstance(buttons, dict):
            values = buttons.get("fields", {}).get("buttons")
            clean_buttons = []
            for value in values if isinstance(values, list) else []:
                if not isinstance(value, dict):
                    continue
                source = _label(value.get("source"))
                label = _label(value.get("label"))
                if source is not None and label is not None:
                    clean_buttons.append({"source": source, "label": label})
            if clean_buttons:
                result["inputs"] = {"buttons": clean_buttons}
        vibration = surfaces.get("vibration")
        if isinstance(vibration, dict):
            result["vibration"] = vibration
        virtual = surfaces.get("virtual_controller")
        if isinstance(virtual, dict):
            result["virtual_controller"] = virtual

        dbus = manager_state.get("dbus")
        if isinstance(dbus, dict):
            last = _operation(dbus.get("last_operation"))
            profile = _operation(dbus.get("profile_apply"))
            if last is not None:
                result["last_operations"]["manager"] = last
            if profile is not None:
                result["last_operations"]["profile"] = profile
        vibration_operation = _operation(manager_state.get("vibration"))
        if vibration_operation is not None:
            result["last_operations"]["vibration"] = vibration_operation
        return result
