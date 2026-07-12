"""Balanced full-color "looks" tuned per panel type. Each sets saturation + the
aesthetic calibration fields together (hue and the per-channel gains stay neutral —
those are white-balance corrections). Applied globally via ColorStore.apply_preset.
A device may override via DeviceProfile.color_presets; else the per-panel set is used."""

from display.const import is_oled

# LCD needs a firmer push (flatter panel, shallower blacks).
_LCD = {
    "cine": {"saturation": 115, "temperature": 12, "contrast": 18, "gamma": -5,
             "vibrance": 15, "black": -12},
    "vivo": {"saturation": 145, "contrast": 20, "vibrance": 40, "black": -8},
    "comodo": {"saturation": 95, "temperature": 35, "contrast": -5, "gamma": 5, "black": 5},
}
# OLED: gentler (already vivid + true blacks).
_OLED = {
    "cine": {"saturation": 108, "temperature": 10, "contrast": 10, "gamma": -3, "vibrance": 10},
    "vivo": {"saturation": 130, "contrast": 12, "vibrance": 30},
    "comodo": {"saturation": 98, "temperature": 30, "contrast": -3, "gamma": 4},
}

# Display order — native first (it's the reset, not a dict).
_ORDER = ("native", "cine", "vivo", "comodo")


def _looks_for(device):
    override = getattr(device, "color_presets", None)
    if isinstance(override, dict) and override:
        return override
    return _OLED if is_oled(device) else _LCD


def preset_keys(device):
    """The look keys available for this device, native first."""
    looks = _looks_for(device)
    return [k for k in _ORDER if k == "native" or k in looks]


def resolve_preset(device, key):
    """The preset dict for a non-native look, or None (native = reset, unknown = no-op)."""
    if key == "native":
        return None
    return _looks_for(device).get(key)
