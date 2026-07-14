"""InputPlumber controller config (SteamOS: Legion Go 1/2, MSI Claw).

Real per-button remap by cooperatively driving the daemon. The remappable buttons
are read DYNAMICALLY from the device's live capabilities (correct per model — the
Legion, Claw, Ally each expose a different set), and an override is applied by
merging it into the device's current profile (preserving defaults) and loading it.
Global (IP profiles are global) — per-game remap is Steam Input's job.
"""
from controllers import ip_profile
from controllers.ip_merge import merge_profile


def get_config(store, dbus, device_key, appid=None, caps=None) -> dict:
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
    buttons = ip_profile.buttons_for(device_key, caps)
    overrides = store.effective_overrides(appid)
    return {
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
    }


def _apply_overrides(dbus, overrides: dict, merge=merge_profile) -> bool:
    """Rebuild the profile from the pristine default (so untouched buttons keep their
    defaults) with `overrides` merged in, and load it. Returns whether it actually
    took effect. `merge` is injectable for tests (the default shells out to the
    system python for the YAML round-trip)."""
    if not dbus.reset_default():
        return False
    if not overrides:
        return True  # reset to the device default IS the applied state
    baseline = dbus.get_profile_yaml()
    if baseline is None:
        return False
    merged = merge(baseline, overrides)
    if not merged:
        return False
    return dbus.load_profile_yaml(merged)


def set_button(store, dbus, device_key, source: str, targets: list,
               scope="global", appid=None, merge=merge_profile) -> dict:
    """Remap one physical button in a scope (global / a game). Ignores a source that
    isn't one of THIS device's remappable buttons; empty/invalid targets revert the
    button to its device default. The store is only updated if the daemon ACTUALLY
    applied the profile, so the reported config can't show a remap the hardware never
    took. The scope tab keeps follow_global in sync, so the edited scope IS the
    running game's effective profile — applying the scope's set applies live."""
    caps = dbus.capabilities()  # read once — reused for the guard and the returned config
    valid = {cap for (cap, _label) in ip_profile.buttons_for(device_key, caps)}
    if source not in valid:
        return get_config(store, dbus, device_key, appid, caps)
    clean = ip_profile.sanitize_targets(targets)
    prospective = store.overrides_for(scope, appid)
    if clean:
        prospective[source] = clean
    else:
        prospective.pop(source, None)
    if _apply_overrides(dbus, prospective, merge=merge):
        store.replace(scope, appid, prospective)
    return get_config(store, dbus, device_key, appid, caps)


def apply_effective(store, dbus, appid, merge=merge_profile) -> bool:
    """Load the effective profile for the running game (its own or global). Used to
    re-assert on game change. Returns whether the daemon took it."""
    return _apply_overrides(dbus, store.effective_overrides(appid), merge=merge)


def reset(store, dbus, device_key=None, scope="global", appid=None) -> dict:
    """Reload InputPlumber's shipped default profile; only forget the scope's
    overrides if it actually reset."""
    if dbus.reset_default():
        store.reset(scope, appid)
    return get_config(store, dbus, device_key, appid)
