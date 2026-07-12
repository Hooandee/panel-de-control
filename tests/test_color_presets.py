from display.presets import preset_keys, resolve_preset


class _Dev:
    def __init__(self, panel="lcd", color_presets=None):
        self.panel = panel
        if color_presets is not None:
            self.color_presets = color_presets


def test_keys_native_first_and_full_set():
    keys = preset_keys(_Dev("lcd"))
    assert keys[0] == "native"
    assert set(keys) == {"native", "cine", "vivo", "comodo"}


def test_native_resolves_to_none():
    assert resolve_preset(_Dev("lcd"), "native") is None


def test_unknown_key_is_none():
    assert resolve_preset(_Dev("lcd"), "nope") is None


def test_look_touches_multiple_fields():
    cine = resolve_preset(_Dev("lcd"), "cine")
    assert cine["saturation"] != 100
    assert cine["contrast"] != 0 and cine["temperature"] != 0


def test_lcd_and_oled_are_tuned_differently():
    assert (resolve_preset(_Dev("lcd"), "vivo")["saturation"]
            != resolve_preset(_Dev("oled"), "vivo")["saturation"])


def test_device_override_wins():
    d = _Dev("lcd", color_presets={"cine": {"saturation": 123}})
    assert resolve_preset(d, "cine")["saturation"] == 123
