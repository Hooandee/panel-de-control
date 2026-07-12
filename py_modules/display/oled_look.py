"""The one-tap "OLED look" color preset per handheld model.

LCD panels on these handhelds look flatter and less saturated than an OLED. This
preset nudges the color toward the punchier OLED look. HONEST framing: it does NOT
give an LCD true per-pixel blacks — it only approximates the *color* feel (more
vibrancy, slightly punchier gamma). The UI copy must say "acerca el color al de un
OLED", never "convierte en OLED".

`GENERIC_OLED_LOOK` is a conservative, safe enhancement applied to any LCD. A model
can carry its own calibrated `oled_look` to override the generic one.
"""

from display.const import is_oled

# Universal LCD enhancement toward the OLED look: a clear vibrancy boost + a
# contrast lift (the real differentiator — OLED's deep blacks read as "pop"),
# neutral temperature. Punchy enough to be obviously different, still tasteful.
GENERIC_OLED_LOOK = {
    "saturation": 140,
    "temperature": 0,
    "contrast": 20,
}
# Contrast kept moderate — a higher value crushes shadow detail on LCD.
# Saturation (140) carries most of the OLED "pop".


def oled_look_for(device):
    """The OLED-look preset for a device, or None if the feature does not apply
    (the device already has an OLED panel). LCD => the device's own calibrated look
    if present, else the generic one."""
    if is_oled(device):
        return None
    return device.oled_look or GENERIC_OLED_LOOK
