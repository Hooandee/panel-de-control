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
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", description="Legion Go EQ")
    assert 'node.name = "Legion Go EQ"' in cfg   # sink shows the friendly name (volume OSD)
    assert "effect_output.pdc_eq" in cfg          # internal output keeps the stable id
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


_CAPS = "/usr/lib/ladspa/caps.so"


def test_bass_node_added_and_chained():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", bass=50, caps=_CAPS)
    assert "label = Spice" in cfg and "caps.so" in cfg
    assert '"lo.gain" = 0.5' in cfg  # 50% → 0.5 drive
    assert '{ output = "eq_band_10:Out" input = "spice:in" }' in cfg


def test_loudness_adds_compressor():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", loudness=True, caps=_CAPS)
    assert "label = Compress" in cfg
    assert '{ output = "eq_band_10:Out" input = "comp:in" }' in cfg


def test_bass_then_compressor_chained_in_order():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", bass=50, loudness=True, caps=_CAPS)
    # eq -> spice -> comp
    assert '{ output = "eq_band_10:Out" input = "spice:in" }' in cfg
    assert '{ output = "spice:out" input = "comp:in" }' in cfg


def test_bass_and_loudness_dropped_without_caps():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", bass=50, loudness=True, caps=None)
    assert "spice" not in cfg and "comp" not in cfg and "caps.so" not in cfg
    assert cfg.count("bq_peaking") == 8


# --- spatial effects: crossfeed (headphones) + stereo width (speakers) ----------------

def test_neutral_stays_mono():
    # crossfeed 0 + width neutral (50) => the classic single mono chain, no explicit io.
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", crossfeed=0, stereo_width=50)
    assert "l_eq_band_1" not in cfg and "r_eq_band_1" not in cfg
    assert "inputs  = [" not in cfg
    assert "eq_band_1:Out" in cfg  # the mono chain
    assert cfg.count("links = [") == 1


def test_crossfeed_builds_stereo_graph():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", crossfeed=100)
    # two explicit channel chains + explicit io mapping
    assert "l_eq_band_1" in cfg and "r_eq_band_10:Out" in cfg
    assert 'inputs  = [ "l_eq_band_1:In" "r_eq_band_1:In" ]' in cfg
    assert 'outputs = [ "cf_mixL:Out" "cf_mixR:Out" ]' in cfg
    # cross-links: left tail feeds the RIGHT ear mixer (and vice-versa)
    assert '{ output = "cf_dL:Out" input = "cf_mixR:In 2" }' in cfg
    assert '{ output = "cf_dR:Out" input = "cf_mixL:In 2" }' in cfg
    # full intensity => 0.6 raw feed, normalised to a unity sum (0.625 + 0.375 = 1.0)
    assert '"Gain 1" = 0.625 "Gain 2" = 0.375' in cfg
    assert "bq_lowpass" in cfg and "label = delay" in cfg


def test_crossfeed_feeds_from_channel_tail_including_effects():
    # crossfeed sits after the per-channel bass+comp tail, not the raw band output
    cfg = build_chain_config(
        gains=[0.0] * 10, sink_name="pdc_eq", bass=50, loudness=True, caps=_CAPS, crossfeed=60
    )
    assert '{ output = "l_comp:out" input = "cf_copyL:In" }' in cfg
    assert '{ output = "r_comp:out" input = "cf_copyR:In" }' in cfg


def test_stereo_width_builds_mid_side_graph():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", stereo_width=100)
    assert "w_mixM" in cfg and "w_mixS" in cfg
    assert cfg.count("label = invert") == 2  # -R for side, -S for right recombine
    assert 'outputs = [ "w_mixL:Out" "w_mixR:Out" ]' in cfg
    # width 100 => w = 2.0 on the side path
    assert '"Gain 1" = 1.0 "Gain 2" = 2.0' in cfg
    # no crossfeed nodes in the width graph
    assert "cf_mixL" not in cfg


def test_narrow_width_below_neutral():
    cfg = build_chain_config(gains=[0.0] * 10, sink_name="pdc_eq", stereo_width=0)
    assert '"Gain 1" = 1.0 "Gain 2" = 0.0' in cfg  # w=0 => mono fold-down
