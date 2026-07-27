from audio.presets import is_tuned, list_presets, resolve_preset


def test_flat_preset_is_zero():
    s = resolve_preset("legion_go_2", "flat", "speaker")
    assert s["gains"] == [0.0] * 10
    assert s["preset"] == "flat"


def test_device_tuned_speaker_corrects():
    s = resolve_preset("legion_go_2", "device_tuned", "speaker")
    assert len(s["gains"]) == 10
    assert any(g != 0.0 for g in s["gains"])  # a real correction curve
    assert s["preamp"] <= 0.0  # headroom for any boosted band


def test_device_tuned_headphone_is_flat():
    # Headphones don't need the internal-speaker correction.
    s = resolve_preset("legion_go_2", "device_tuned", "headphone")
    assert s["gains"] == [0.0] * 10


def test_unknown_device_falls_back():
    s = resolve_preset("some_unknown", "voices", "speaker")
    assert len(s["gains"]) == 10


def test_list_includes_hero_first_for_known_device():
    presets = list_presets("legion_go_2")
    assert presets[0]["id"] == "device_tuned"
    assert presets[0]["tuned"] is True  # a real per-model curve
    ids = [p["id"] for p in presets]
    assert "flat" in ids and "voices" in ids


def test_hero_always_offered_as_starting_point_for_unknown_device():
    presets = list_presets("some_unknown")
    assert presets[0]["id"] == "device_tuned"
    assert presets[0]["tuned"] is False  # generic correction, not model-tuned yet


def test_unknown_device_hero_is_a_real_correction_not_flat():
    s = resolve_preset("some_unknown", "device_tuned", "speaker")
    assert any(g != 0.0 for g in s["gains"])  # a starting-point correction, still applied
    assert s["preamp"] <= 0.0


def test_is_tuned_reflects_the_device_table():
    assert is_tuned("legion_go") is True
    assert is_tuned("some_unknown") is False
