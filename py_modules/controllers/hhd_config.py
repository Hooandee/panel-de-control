"""Handheld Daemon controller config (Bazzite: ROG Ally family).

HHD owns the controller and delegates FINE per-button remap to Steam Input, so the
useful cooperative surface here is coarser: the emulated controller mode and the
paddle behavior. We read/write HHD's own settings via its REST API (the same path
its frontend uses) — pure builders here, the HTTP lives in hhd.py.

The device key under `controllers` (e.g. "rog_ally") is read from the live state,
never hardcoded, so an ASUS variant with a different key still works.
"""

from controllers.capabilities import clean_report, report, surface

# Emulated controller modes HHD offers, in display order.
MODES = ("uinput", "hori_steam", "dualsense", "hidden")
# Paddle behavior options (only the uinput/dualsense modes expose paddles_as).
PADDLES_AS = ("steam_input", "noob", "disabled")
_PADDLE_MODES = ("uinput", "dualsense")
_VIBRATION_KEYS = {"rog_ally", "rog_ally_x"}
_CAPABILITY_MODES = (
    "uinput", "xbox_elite", "hori_steam", "dualsense", "hidden",
    "disabled",
)
_CAPABILITY_PADDLES = (
    "steam_input", "noob", "touchpad", "both", "disabled",
)


def device_key(state) -> str | None:
    """The single key under `controllers` in HHD's state (the device id)."""
    controllers = (state or {}).get("controllers")
    if not isinstance(controllers, dict) or not controllers:
        return None
    return next(iter(controllers))


def get_config(state) -> dict:
    key = device_key(state)
    if not key:
        return {"kind": "none"}
    cm = state["controllers"][key].get("controller_mode", {})
    mode = cm.get("mode")
    paddles = cm.get(mode, {}).get("paddles_as") if mode in _PADDLE_MODES else None
    return {
        "kind": "settings",
        "device_key": key,
        "mode": mode,
        "mode_options": list(MODES),
        "paddles_as": paddles,
        "paddles_options": list(PADDLES_AS),
    }


def _mode_schema(settings, key):
    controllers = (settings or {}).get("controllers")
    if not isinstance(controllers, dict):
        return None
    controller = controllers.get(key)
    if not isinstance(controller, dict):
        return None
    children = controller.get("children")
    if not isinstance(children, dict):
        return None
    mode = children.get("controller_mode")
    if not isinstance(mode, dict) or mode.get("type") != "mode":
        return None
    modes = mode.get("modes")
    return modes if isinstance(modes, dict) else None


def _schema_matches_state(settings, state):
    settings_version = (settings or {}).get("version")
    state_version = (state or {}).get("version")
    if settings_version is None or state_version is None:
        return True
    return settings_version == state_version


def capabilities_report(state, device_profile_key, settings=None) -> dict:
    key = device_key(state)
    if key is None:
        return clean_report(report(device_profile_key, "hhd", {}))
    controller = state["controllers"].get(key)
    if not isinstance(controller, dict):
        return clean_report(report(device_profile_key, "hhd", {}))

    surfaces = {}
    controller_mode = controller.get("controller_mode")
    modes_schema = (
        _mode_schema(settings, key)
        if _schema_matches_state(settings, state)
        else None
    )
    if isinstance(controller_mode, dict) and isinstance(modes_schema, dict):
        mode = controller_mode.get("mode")
        mode_options = [
            candidate
            for candidate in _CAPABILITY_MODES
            if isinstance(modes_schema.get(candidate), dict)
        ]
        if isinstance(mode, str) and mode in mode_options:
            mode_state = controller_mode.get(mode)
            mode_state = mode_state if isinstance(mode_state, dict) else {}
            paddles = mode_state.get("paddles_as")
            mode_children = modes_schema[mode].get("children")
            mode_children = (
                mode_children if isinstance(mode_children, dict) else {}
            )
            paddles_schema = mode_children.get("paddles_as")
            schema_options = (
                paddles_schema.get("options")
                if isinstance(paddles_schema, dict)
                else None
            )
            paddles_options = [
                candidate
                for candidate in _CAPABILITY_PADDLES
                if isinstance(schema_options, dict)
                and candidate in schema_options
            ]
            surfaces["settings"] = surface(
                "hhd",
                "supported",
                fields={
                    "mode": mode,
                    "mode_options": mode_options,
                    "paddles_as": (
                        paddles if paddles in paddles_options else None
                    ),
                    "paddles_options": paddles_options,
                },
                scope=("global",),
                apply="recreate",
                readback="accepted",
                evidence="upstream",
            )

    vibration = vibration_state(state, device_profile_key)
    if vibration is not None:
        surfaces["vibration"] = surface(
            "hhd",
            "supported",
            fields={
                field: value
                for field, value in vibration.items()
                if field not in {"device_key", "readback"}
            },
            scope=("global", "game"),
            apply="hot",
            readback="accepted",
            evidence="upstream",
        )
    return clean_report(report(device_profile_key, "hhd", surfaces))


def build_payload(device_key: str, mode: str, field: str, value: str) -> dict:
    """Minimal partial-state POST body for one setting (HHD merges partials)."""
    if field == "mode":
        return {"controllers": {device_key: {"controller_mode": {"mode": value}}}}
    if field == "paddles_as":
        # paddles_as lives under the ACTIVE mode's subtree.
        return {"controllers": {device_key: {"controller_mode": {mode: {"paddles_as": value}}}}}
    return {}


def apply_setting(state, field: str, value: str) -> dict:
    """Build the POST body for one setting from the live state, resolving the device
    key + active mode itself (the RPC shouldn't need to know HHD's nested shape).
    Empty dict if the state has no controller (nothing to write)."""
    key = device_key(state)
    if not key:
        return {}
    mode = state["controllers"][key].get("controller_mode", {}).get("mode")
    return build_payload(key, mode, field, value)


def vibration_state(state, device_profile_key):
    """Read HHD's owned Ally vibration control from its live config tree."""
    if device_profile_key not in _VIBRATION_KEYS:
        return None
    key = device_key(state)
    if key is None:
        return None
    limits = state["controllers"][key].get("limits")
    if not isinstance(limits, dict):
        return None
    # `limits` is one HHD mode containing vibration and every stick/trigger
    # deadzone. Never switch it to manual behind HHD's back: that could change
    # unrelated limits. We cooperate only when the user already selected manual.
    if limits.get("mode") != "manual":
        return None
    value = (limits.get("manual") or {}).get("vibration")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    value = min(100, max(0, round(float(value))))
    return {
        "device_key": key,
        "mode": "gain",
        "persistent": True,
        "value": value,
        "min": 0,
        "max": 100,
        "step": 20,
        "readback": False,
    }


def vibration_payload(state, value) -> dict:
    key = device_key(state)
    if key is None:
        return {}
    limits = state["controllers"][key].get("limits")
    if not isinstance(limits, dict) or limits.get("mode") != "manual":
        return {}
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return {}
    clean = min(100, max(0, round(float(value))))
    return {
        "controllers": {
            key: {
                "limits": {
                    "manual": {"vibration": clean},
                }
            }
        }
    }
