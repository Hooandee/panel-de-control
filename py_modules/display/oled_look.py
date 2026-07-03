"""The one-tap "OLED look" color preset per handheld model.

LCD panels on these handhelds look flatter and less saturated than an OLED. This
preset nudges the color toward the punchier OLED look. HONEST framing: it does NOT
give an LCD true per-pixel blacks — it only approximates the *color* feel (more
vibrancy, slightly punchier gamma). The UI copy must say "acerca el color al de un
OLED", never "convierte en OLED".

`GENERIC_OLED_LOOK` is a conservative, safe enhancement applied to any LCD. A model
can carry its own `oled_look` (calibrated ON-DEVICE) to override the generic one.
"""

# Universal LCD enhancement toward the OLED look: a clear vibrancy boost + a
# contrast lift (the real differentiator — OLED's deep blacks read as "pop"),
# neutral temperature. Punchy enough to be obviously different, still tasteful.
# Per-model tuning refines it later (validated on real hardware, never invented).
GENERIC_OLED_LOOK = {
    "saturation": 140,
    "temperature": 0,
    "contrast": 20,
}
# NOTE: contrast kept moderate — a +30 crushed shadow detail on the Ally LCD
# (validated 2026-07-03). Saturation (140) carries most of the OLED "pop".


def oled_look_for(device):
    """The OLED-look preset for a device, or None if the feature does not apply
    (the device already has an OLED panel). LCD => the device's own calibrated look
    if present, else the generic one."""
    if getattr(device, "panel", "lcd") == "oled":
        return None
    return device.oled_look or GENERIC_OLED_LOOK
