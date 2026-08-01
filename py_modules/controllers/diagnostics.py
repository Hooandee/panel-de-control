"""Read-only, redacted diagnostics for the selected integrated controller."""

import re

from controllers.capabilities import clean_report


_OPERATION_FIELDS = {
    "operation", "owner", "mode", "ok", "reason", "enabled", "strength",
    "profile_bytes", "rollback_confirmed", "readback", "echoed_value",
}
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+()'-]{0,63}")


def _label(value):
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else None


def _scalar(value):
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, str):
        return _label(value) is not None
    return (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _operation(value):
    if not isinstance(value, dict):
        return None
    clean = {
        key: item
        for key, item in value.items()
        if key in _OPERATION_FIELDS and _scalar(item)
    }
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
                if _label(name) is not None:
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
