"""Handheld Daemon controller config (Bazzite: ROG Ally family).

HHD owns the controller and delegates FINE per-button remap to Steam Input, so the
useful cooperative surface here is coarser: the emulated controller mode and the
paddle behavior. We read/write HHD's own settings via its REST API (the same path
its frontend uses) — pure builders here, the HTTP lives in hhd.py.

The device key under `controllers` (e.g. "rog_ally") is read from the live state,
never hardcoded, so an ASUS variant with a different key still works.
"""

# Emulated controller modes HHD offers, in display order.
MODES = ("uinput", "hori_steam", "dualsense", "hidden")
# Paddle behavior options (only the uinput/dualsense modes expose paddles_as).
PADDLES_AS = ("steam_input", "noob", "disabled")
_PADDLE_MODES = ("uinput", "dualsense")


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
