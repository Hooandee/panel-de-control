"""InputPlumber controller config (SteamOS: Legion Go 1/2, MSI Claw).

Real per-button remap by cooperatively driving the daemon. The remappable buttons
are read DYNAMICALLY from the device's live capabilities (correct per model — the
Legion, Claw, Ally each expose a different set), and an override is applied by
merging it into the device's captured profile (preserving defaults) and loading it.
The plugin re-applies its own global/per-game intent on game transitions while
retaining foreign mappings and auxiliary virtual devices.
"""
from controllers import ip_profile
from controllers.capabilities import clean_report, report, surface
from controllers.ip_merge import merge_profile
from controllers.ip_merge import profiles_equal as ip_profile_profiles_equal


def _vibration_capabilities(vibration, ff_enabled=None):
    describe = getattr(vibration, "capabilities", None)
    if callable(describe):
        return describe()
    state = vibration.state() if vibration is not None else None
    if isinstance(state, dict) and state.get("mode") == "dual":
        return {
            "mode": "dual", "channels": ["left", "right"],
            "readback": "driver", "min": 0, "max": 100, "step": 5,
            "test": {
                "patterns": ["pulse"],
                "channels": ["left", "right", "both"],
            },
        }
    if isinstance(state, dict) and state.get("mode") == "gain":
        return {
            "mode": "gain", "channels": [], "readback": "none",
            "min": 0, "max": 100, "step": 5,
            "test": {"patterns": ["pulse"], "channels": ["both"]},
        }
    if isinstance(ff_enabled, bool):
        return {
            "mode": "enabled_only", "channels": [], "readback": "none",
            "test": {"patterns": ["pulse"], "channels": ["both"]},
        }
    return None


def live_buttons(dbus, device_key, capabilities):
    proven = set()
    if ip_profile.needs_mapped_capability_proof(device_key):
        source_paths = getattr(
            dbus, "source_device_paths", lambda: []
        )()
        proven = ip_profile.proven_mapped_capabilities(
            device_key, source_paths
        )
    return ip_profile.buttons_for(device_key, capabilities, proven)


def capabilities_report(dbus, device_key, vibration=None,
                        virtual_mode=None) -> dict:
    buttons = live_buttons(dbus, device_key, dbus.capabilities())
    surfaces = {}
    if buttons:
        surfaces["buttons"] = surface(
            "inputplumber",
            "supported",
            fields={
                "buttons": [
                    {"source": source, "label": label}
                    for source, label in buttons
                ],
                "gamepad_targets": list(ip_profile.GAMEPAD_TARGETS),
                "key_targets": list(ip_profile.KEY_TARGETS),
            },
            scope=("global", "game"),
            apply="hot",
            readback="exact",
            evidence="upstream",
        )

    virtual_capabilities = (
        virtual_mode.capabilities()
        if virtual_mode is not None else None
    )
    if virtual_capabilities is not None:
        surfaces["virtual_controller"] = surface(
            "inputplumber",
            "supported",
            fields={
                "options": list(virtual_capabilities["options"]),
                "actual_mode": virtual_capabilities["current"],
                "readiness": virtual_capabilities["readiness"],
            },
            scope=("global", "game"),
            apply="recreate",
            readback="exact",
            evidence="upstream",
        )

    read_force_feedback = getattr(dbus, "force_feedback_enabled", None)
    ff_enabled = (
        read_force_feedback() if callable(read_force_feedback) else None
    )
    vibration_capabilities = _vibration_capabilities(
        vibration, ff_enabled
    )
    if (
        isinstance(vibration_capabilities, dict)
        and vibration_capabilities.get("mode") != "unavailable"
    ):
        mode = vibration_capabilities["mode"]
        exact = vibration_capabilities.get("readback") == "driver"
        owner = {
            "dual": "native",
            "gain": "evdev",
        }.get(mode, "inputplumber")
        surfaces["vibration"] = surface(
            owner,
            "supported",
            fields=dict(vibration_capabilities),
            scope=("global", "game"),
            apply="hot",
            readback="exact" if exact else "accepted",
            evidence="upstream",
        )
    return clean_report(report(device_key, "inputplumber", surfaces))


def get_config(store, dbus, device_key, appid=None, caps=None, vibration=None,
               apply_status=None, virtual_mode=None) -> dict:
    """The device's remappable physical buttons (per-device silkscreen table, gated
    by the live capabilities) + each one's EFFECTIVE override for the running game
    (its own when it has one, else global; None = still at the device default) + the
    target vocabulary the UI offers. Reading the effective set (not a raw scope) keeps
    the shown buttons in lock-step with the scope tab, which drives follow_global.
    `device_known` is False for a device we don't have a button map for, so the UI
    can say so honestly instead of showing phantom buttons. `caps` lets a caller that
    already read the live capabilities (set_button) avoid a second `busctl` spawn.
    `follows_global`/`has_game_profile` drive the per-game scope tab."""
    if caps is None:
        caps = dbus.capabilities()
    buttons = live_buttons(dbus, device_key, caps)
    overrides = store.effective_overrides(appid)
    identified = bool(ip_profile.composite_names_for(device_key))
    read_force_feedback = getattr(dbus, "force_feedback_enabled", None)
    ff_enabled = (
        read_force_feedback()
        if identified and callable(read_force_feedback)
        else None
    )
    vibration_capabilities = (
        _vibration_capabilities(vibration, ff_enabled)
        if identified else None
    )
    test = (
        vibration_capabilities.get("test", {})
        if isinstance(vibration_capabilities, dict)
        else {}
    )
    vibration_config = {
        "supported": ff_enabled is not None,
        "enabled": ff_enabled,
        "test_supported": bool(test.get("patterns") and test.get("channels")),
        "test_patterns": list(test.get("patterns", [])),
        "test_channels": list(test.get("channels", [])),
    }
    if isinstance(vibration_capabilities, dict):
        vibration_config["confirmation"] = vibration_capabilities.get(
            "readback", "none"
        )
    persistent_state = (
        vibration.state()
        if identified and vibration is not None
        else None
    )
    if persistent_state is not None:
        desired = store.effective_vibration(appid)
        vibration_config.update(persistent_state)
        vibration_config["supported"] = True
        if persistent_state["mode"] == "dual":
            vibration_config["actual_left"] = persistent_state["left"]
            vibration_config["actual_right"] = persistent_state["right"]
            vibration_config["left"] = desired.get(
                "left", persistent_state["left"]
            )
            vibration_config["right"] = desired.get(
                "right", persistent_state["right"]
            )
        elif persistent_state["mode"] == "gain":
            vibration_config["actual_value"] = persistent_state.get("value")
            vibration_config["value"] = desired.get("value", 100)
    if apply_status is not None:
        vibration_config["last_apply"] = bool(apply_status)
    config = {
        "kind": "remap",
        "device_known": ip_profile.is_known_device(device_key),
        "buttons": [
            {"source": cap, "label": label, "target": overrides.get(cap)}
            for (cap, label) in buttons
        ],
        "gamepad_targets": list(ip_profile.GAMEPAD_TARGETS),
        "key_targets": list(ip_profile.KEY_TARGETS),
        "follows_global": store.is_following_global(appid),
        "has_game_profile": store.has_game(appid),
        "virtual_controller": (
            virtual_mode.config(appid)
            if virtual_mode is not None
            else {
                "supported": False, "mode": "auto",
                "actual_mode": None, "options": [], "scope": [],
            }
        ),
        "vibration": vibration_config,
    }
    profile_status = getattr(
        dbus, "profile_apply_status", lambda: None
    )()
    if profile_status is not None:
        config["last_apply"] = profile_status.get("ok")
        if profile_status.get("reason"):
            config["apply_error"] = profile_status["reason"]
    return config


def _apply_overrides(store, dbus, device_key, overrides: dict,
                     merge=merge_profile,
                     equivalent=ip_profile_profiles_equal) -> bool:
    """Apply against the profile captured before this plugin took ownership.

    The baseline includes foreign mappings and keys. Later writes require the live
    profile to equal our last readback, so another editor makes us stop instead of
    silently overwriting its changes. Empty overrides restore the baseline.
    """
    def record(ok, reason=None, **details):
        callback = getattr(dbus, "record_profile_apply", None)
        if callable(callback):
            callback(ok, reason, **details)

    current = dbus.get_profile_yaml()
    if current is None:
        record(False, "profile_unavailable")
        return False
    state = store.profile_state(device_key)
    created_state = state is None
    if state is None:
        baseline = current
        store.remember_profile_baseline(device_key, baseline)
    else:
        baseline = state["baseline_yaml"]
        expected = state.get("last_applied_yaml") or baseline
        owned_candidates = [
            baseline,
            expected,
            *(state.get("recovery_yamls") or []),
        ]
        if not any(
            equivalent(current, candidate)
            for candidate in owned_candidates
        ):
            record(False, "profile_conflict")
            return False

    merged = merge(baseline, overrides)
    if not merged:
        if created_state:
            store.forget_profile_state(device_key)
        record(False, "merge_failed")
        return False
    managed = bool(overrides)
    if equivalent(current, merged):
        if managed:
            store.remember_applied_profile(device_key, current)
        else:
            store.forget_profile_state(device_key)
        record(True, changed=False)
        return True
    loaded = dbus.load_profile_yaml(merged)
    if loaded:
        applied = dbus.get_profile_yaml()
        if applied is not None and equivalent(applied, merged):
            if managed:
                store.remember_applied_profile(device_key, applied)
            else:
                store.forget_profile_state(device_key)
            record(True)
            return True
    rollback_loaded = dbus.load_profile_yaml(current)
    rollback = dbus.get_profile_yaml() if rollback_loaded else None
    rollback_confirmed = (
        rollback is not None and equivalent(rollback, current)
    )
    if rollback_confirmed and created_state:
        store.forget_profile_state(device_key)
    elif not rollback_confirmed:
        candidates = [current]
        if loaded:
            candidates.append(merged)
        store.remember_profile_recovery(device_key, candidates)
    record(
        False,
        "readback_mismatch" if loaded else "load_failed",
        rollback_confirmed=rollback_confirmed,
    )
    return False


def set_button(store, dbus, device_key, source: str, targets: list,
               scope="global", appid=None, vibration=None,
               merge=merge_profile, virtual_mode=None) -> dict:
    """Remap one physical button in a scope (global / a game). Ignores a source that
    isn't one of THIS device's remappable buttons; empty/invalid targets revert the
    button to its device default. The store is only updated if the daemon ACTUALLY
    applied the profile, so the reported config can't show a remap the hardware never
    took. The scope tab keeps follow_global in sync, so the edited scope IS the
    running game's effective profile — applying the scope's set applies live."""
    caps = dbus.capabilities()  # read once — reused for the guard and the returned config
    valid = {
        cap for (cap, _label) in live_buttons(dbus, device_key, caps)
    }
    if source not in valid:
        return get_config(
            store, dbus, device_key, appid, caps, vibration=vibration,
            virtual_mode=virtual_mode,
        )
    clean = ip_profile.sanitize_button_action(targets)
    if targets and not clean:
        return get_config(
            store, dbus, device_key, appid, caps, vibration=vibration,
            virtual_mode=virtual_mode,
        )
    prospective = store.overrides_for(scope, appid)
    if clean:
        prospective[source] = clean
    else:
        prospective.pop(source, None)
    applied = _apply_overrides(
        store, dbus, device_key, prospective, merge=merge,
    )
    if applied:
        store.replace(scope, appid, prospective)
        return get_config(
            store, dbus, device_key, appid, caps, vibration=vibration,
            virtual_mode=virtual_mode,
        )
    return get_config(
        store, dbus, device_key, appid, vibration=vibration,
        virtual_mode=virtual_mode,
    )


def _persistent_values(controller, desired):
    state = controller.state() if controller is not None else None
    if state is None:
        return None
    if state["mode"] == "dual":
        return {
            "left": desired.get("left", state["left"]),
            "right": desired.get("right", state["right"]),
        }
    if state["mode"] == "gain" and "value" in desired:
        return {"value": desired["value"]}
    return None


def _vibration_owner(device_key):
    return f"inputplumber:{device_key or ''}"


def _ensure_vibration_baseline(store, dbus, device_key, state, vibration=None):
    current = store.vibration_for("global")
    observed = {}
    enabled = dbus.force_feedback_enabled()
    if enabled is not None:
        observed["enabled"] = enabled
    if state is not None and state["mode"] == "dual":
        observed["left"] = state["left"]
        observed["right"] = state["right"]
        capture = getattr(vibration, "capture_baseline", None)
        native = capture() if callable(capture) else {}
        if (
            isinstance(native, dict)
            and "native_left" in native
            and "native_right" in native
        ):
            observed.update(native)
    elif state is not None and state["mode"] == "gain":
        # EV_FF exposes no gain readback. Use an explicit plugin-owned, unattenuated
        # baseline; the UI reports this as desired/accepted, never as actual state.
        observed["value"] = 100
    store.remember_vibration_baseline(
        _vibration_owner(device_key), observed
    )
    baseline = {
        field: value
        for field, value in observed.items()
        if field not in current
    }
    if baseline:
        store.patch_vibration("global", None, baseline)


def _apply_vibration(dbus, vibration, desired) -> bool:
    enabled_applied = (
        dbus.set_force_feedback_enabled(desired["enabled"])
        if "enabled" in desired
        else True
    )
    persistent = _persistent_values(vibration, desired)
    intensity_applied = (
        vibration.apply(persistent) if persistent is not None else True
    )
    return enabled_applied and intensity_applied


def apply_effective_components(store, dbus, device_key, appid,
                               vibration=None, apply_buttons=True,
                               merge=merge_profile) -> dict:
    """Load the effective profile for the running game (its own or global). Used to
    re-assert on game change, retaining confirmation per independent component."""
    if not ip_profile.composite_names_for(device_key):
        return {"buttons": False, "vibration": False}
    buttons_applied = (
        not apply_buttons
        or _apply_overrides(
            store, dbus, device_key, store.effective_overrides(appid),
            merge=merge,
        )
    )
    desired = store.effective_vibration(appid)
    if desired:
        state = vibration.state() if vibration is not None else None
        _ensure_vibration_baseline(
            store, dbus, device_key, state, vibration
        )
        desired = store.effective_vibration(appid)
    vibration_applied = _apply_vibration(
        dbus, vibration, desired
    )
    return {
        "buttons": buttons_applied,
        "vibration": vibration_applied,
    }


def apply_effective(store, dbus, device_key, appid, vibration=None,
                    apply_buttons=True, merge=merge_profile) -> bool:
    status = apply_effective_components(
        store, dbus, device_key, appid, vibration, apply_buttons, merge
    )
    return status["buttons"] and status["vibration"]


def restore_external(store, dbus, device_key, vibration=None) -> bool:
    """Restore the immutable state captured before the plugin took ownership."""
    if not ip_profile.composite_names_for(device_key):
        return False
    buttons_applied = (
        _apply_overrides(store, dbus, device_key, {})
        if store.profile_state(device_key) is not None
        else True
    )
    baseline = store.vibration_baseline(_vibration_owner(device_key))
    enabled_applied = (
        dbus.set_force_feedback_enabled(baseline["enabled"])
        if "enabled" in baseline
        else True
    )
    restore = getattr(vibration, "restore_baseline", None)
    native_baseline = (
        "native_left" in baseline and "native_right" in baseline
    )
    if native_baseline and callable(restore):
        intensity_applied = restore(baseline)
    else:
        persistent = _persistent_values(vibration, baseline)
        intensity_applied = (
            vibration.apply(persistent)
            if persistent is not None
            else True
        )
    vibration_applied = enabled_applied and intensity_applied
    return buttons_applied and vibration_applied


def reset(store, dbus, device_key=None, scope="global", appid=None,
          vibration=None, merge=merge_profile, virtual_mode=None) -> dict:
    """Restore the plugin-captured profile without touching foreign mappings."""
    prospective = store.overrides_for(scope, appid)
    prospective.clear()
    if _apply_overrides(
        store, dbus, device_key, prospective, merge=merge,
    ):
        store.reset(scope, appid)
    return get_config(
        store, dbus, device_key, appid, vibration=vibration,
        virtual_mode=virtual_mode,
    )


def set_vibration(store, dbus, device_key, patch: dict, scope="global",
                  appid=None, vibration=None, virtual_mode=None) -> dict:
    if (
        not ip_profile.composite_names_for(device_key)
        or not isinstance(patch, dict)
    ):
        return get_config(
            store, dbus, device_key, appid, vibration=vibration,
            virtual_mode=virtual_mode,
        )
    allowed = {}
    if isinstance(patch.get("enabled"), bool):
        allowed["enabled"] = patch["enabled"]
    state = vibration.state() if vibration is not None else None
    if state is not None:
        fields = ("left", "right") if state["mode"] == "dual" else ("value",)
        for field in fields:
            value = patch.get(field)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                allowed[field] = value
    if not allowed:
        return get_config(
            store, dbus, device_key, appid, vibration=vibration,
            virtual_mode=virtual_mode,
        )

    _ensure_vibration_baseline(
        store, dbus, device_key, state, vibration
    )
    store.patch_vibration(scope, appid, allowed)
    desired = store.effective_vibration(appid)
    results = []
    if "enabled" in allowed:
        results.append(dbus.set_force_feedback_enabled(desired["enabled"]))
    if any(field in allowed for field in ("value", "left", "right")):
        persistent = _persistent_values(vibration, desired)
        results.append(
            vibration.apply(persistent) if persistent is not None else False
        )
    applied = all(results)
    return get_config(
        store, dbus, device_key, appid, vibration=vibration,
        apply_status=applied, virtual_mode=virtual_mode,
    )


def test_vibration(vibration, pattern="pulse", channel=None, strength=100):
    return vibration.test(pattern, channel, strength)
