"""Shared color model constants (single source of truth for the panel-color
feature). Both the persistence layer (color_store) and the LUT math (gamescope)
import from here so the neutral baseline + field set can't drift."""

# The panel's native/neutral look. saturation is unipolar (100 = neutral);
# temperature/contrast are bipolar (0 = neutral).
NATIVE = {"saturation": 100, "temperature": 0, "contrast": 0}

# The color fields, in stable order (state payload / iteration).
FIELDS = tuple(NATIVE)
