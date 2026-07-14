from audio.presets import list_presets, resolve_preset


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
    ids = [p["id"] for p in list_presets("legion_go_2")]
    assert ids[0] == "device_tuned"
    assert "flat" in ids and "voices" in ids


def test_list_no_hero_for_unknown_device():
    ids = [p["id"] for p in list_presets("some_unknown")]
    assert "device_tuned" not in ids
    assert "flat" in ids
