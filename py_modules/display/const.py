"""Color model constants: the field set and its neutral baseline, shared by the store
and the LUT math so they can't drift. Missing fields read as neutral, so older saved
files load safe. saturation is per-game; everything else is global calibration."""

NATIVE = {
    "saturation": 100,  # unipolar, 100 = neutral
    "temperature": 0,
    "contrast": 0,
    "gamma": 0,
    "hue": 0,
    "black": 0,
    "gain_r": 100,      # per-channel gains: 100 = 1.0
    "gain_g": 100,
    "gain_b": 100,
    "vibrance": 0,
}

FIELDS = tuple(NATIVE)
CALIBRATION = tuple(f for f in NATIVE if f != "saturation")


def is_oled(device):
    return getattr(device, "panel", "lcd") == "oled"
