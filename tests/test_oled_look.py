from device_registry import detect
from display.oled_look import GENERIC_OLED_LOOK, oled_look_for

_COLOR_FIELDS = {"saturation", "temperature", "contrast"}


def test_oled_panels_have_no_look_feature():
    # A real OLED gets nothing to "look like" — the feature is N/A there.
    assert detect(product_name="Galileo").panel == "oled"        # Steam Deck OLED
    assert oled_look_for(detect(product_name="Galileo")) is None


def test_lcd_panels_get_the_generic_look():
    ally = detect(product_name="ROG Ally X RC72LA_RC72LA")
    assert ally.panel == "lcd"
    assert oled_look_for(ally) == GENERIC_OLED_LOOK


def test_generic_look_is_a_valid_in_range_color_state():
    assert set(GENERIC_OLED_LOOK) == _COLOR_FIELDS
    assert 100 < GENERIC_OLED_LOOK["saturation"] <= 200   # a clear vibrancy boost
    assert GENERIC_OLED_LOOK["contrast"] > 0               # the OLED "pop" differentiator
    assert -100 <= GENERIC_OLED_LOOK["temperature"] <= 100


def test_per_model_override_wins_when_present():
    # Forward-compat: a device carrying its own calibrated look uses it, not generic.
    from device_profiles import DeviceProfile
    tuned = {"saturation": 135, "temperature": -8, "contrast": 25}
    dev = DeviceProfile("x", "X", "chip", "amd", 5, 10, 15, 15,
                        panel="lcd", oled_look=tuned)
    assert oled_look_for(dev) == tuned
