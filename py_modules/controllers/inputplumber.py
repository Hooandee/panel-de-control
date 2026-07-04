"""InputPlumber controller config (SteamOS: Legion Go 1/2, MSI Claw).

Real per-button remap by cooperatively driving the daemon. The remappable buttons
are read DYNAMICALLY from the device's live capabilities (correct per model — the
Legion, Claw, Ally each expose a different set), and an override is applied by
merging it into the device's current profile (preserving defaults) and loading it.
Global (IP profiles are global) — per-game remap is Steam Input's job.
"""
from controllers import ip_profile
from controllers.ip_merge import merge_profile


def get_config(store, dbus, device_key, caps=None) -> dict:
    """The device's remappable physical buttons (per-device silkscreen table, gated
    by the live capabilities) + each one's current override (or None = still at the
    device default) + the target vocabulary the UI offers. `device_known` is False
    for a device we haven't validated on-hardware, so the UI can say so honestly
    instead of showing phantom buttons. `caps` lets a caller that already read the
    live capabilities (set_button) avoid a second `busctl` spawn."""
    if caps is None:
        caps = dbus.capabilities()
    buttons = ip_profile.buttons_for(device_key, caps)
    overrides = store.all()
    return {
        "kind": "remap",
        "device_known": ip_profile.is_known_device(device_key),
        "buttons": [
            {"source": cap, "label": label, "target": overrides.get(cap)}
            for (cap, label) in buttons
        ],
        "gamepad_targets": list(ip_profile.GAMEPAD_TARGETS),
        "key_targets": list(ip_profile.KEY_TARGETS),
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


def set_button(store, dbus, device_key, source: str, targets: list, merge=merge_profile) -> dict:
    """Remap one physical button. Ignores a source that isn't one of THIS device's
    remappable buttons; empty/invalid targets revert the button to its device
    default. Never-fake: the store is only updated if the daemon ACTUALLY applied the
    profile, so the reported config can't show a remap the hardware never took."""
    caps = dbus.capabilities()  # read once — reused for the guard and the returned config
    valid = {cap for (cap, _label) in ip_profile.buttons_for(device_key, caps)}
    if source not in valid:
        return get_config(store, dbus, device_key, caps)
    clean = ip_profile.sanitize_targets(targets)
    prospective = dict(store.all())
    if clean:
        prospective[source] = clean
    else:
        prospective.pop(source, None)
    if _apply_overrides(dbus, prospective, merge=merge):
        store.replace(prospective)
    return get_config(store, dbus, device_key, caps)


def reset(store, dbus, device_key=None) -> dict:
    """Reload InputPlumber's shipped default profile; only forget the overrides if it
    actually reset (never-fake)."""
    if dbus.reset_default():
        store.reset()
    return get_config(store, dbus, device_key)
