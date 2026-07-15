from audio.const import BAND_FREQS
from audio.filter_chain import build_chain_config


def test_has_ten_bands_at_band_freqs():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq")
    for f in BAND_FREQS:
        assert f'"Freq" = {f}' in cfg
    # first band = lowshelf, last = highshelf, the rest peaking
    assert cfg.count("bq_peaking") == 8
    assert cfg.count("bq_lowshelf") == 1
    assert cfg.count("bq_highshelf") == 1


def test_sink_name_and_class():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq")
    assert "effect_input.pdc_eq" in cfg
    assert "media.class = Audio/Sink" in cfg
    assert "node.passive = true" in cfg


def test_gains_are_embedded():
    gains = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    cfg = build_chain_config(gains=gains, sink_name="pdc_eq")
    for g in gains:
        assert f'"Gain" = {float(g)}' in cfg


def test_bands_are_chained_in_order():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq")
    assert cfg.count("links = [") == 1
    assert '"eq_band_1:Out"' in cfg and '"eq_band_10:In"' in cfg


def test_no_bass_node_when_zero():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", bass=0)
    assert "spice" not in cfg and "caps.so" not in cfg


def test_bass_node_added_and_chained():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", bass=50)
    assert "label = Spice" in cfg and "caps.so" in cfg
    assert '"lo.gain" = 0.5' in cfg  # 50% → 0.5 drive
    assert '{ output = "eq_band_10:Out" input = "spice:In" }' in cfg
