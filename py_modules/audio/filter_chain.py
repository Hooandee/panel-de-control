"""Builds the PipeWire filter-chain config text for the EQ sink: 10 biquad bands
(lowshelf at the bottom, highshelf at the top, peaking in between) in series, optionally
followed by a CAPS Spice bass enhancer + a compressor.

Two shapes: with no spatial effect the graph is a single mono chain that PipeWire
duplicates onto FL/FR (the classic EQ). When crossfeed (headphones) or stereo width
(speakers) is engaged the chain becomes explicitly stereo: separate L/R band chains feed
a cross-channel stage. Pure string building — writing/loading the conf and restarting the
service live in the PipeWire lifecycle module."""

from audio.const import (
    BAND_FREQS,
    CROSSFEED_DELAY_S,
    CROSSFEED_LOWPASS_HZ,
    CROSSFEED_LOWPASS_Q,
    WIDTH_NEUTRAL,
    clamp_pct,
    crossfeed_gain,
    width_factor,
)

_LABELS = ["bq_lowshelf"] + ["bq_peaking"] * 8 + ["bq_highshelf"]

_BASS_FREQ = 130
_BASS_MAX_DRIVE = 1.0

_COMP = '{ "threshold" = -18 "strength" = 0.6 "attack" = 20 "release" = 200 "gain (dB)" = 6 }'

# Mono CAPS effects (not the X2 stereo variants) so they duplicate per channel like the
# mono biquads. Their audio ports are lowercase in/out (LADSPA), not the builtin In/Out.


def _channel_chain(gains, bass, loudness, caps, prefix=""):
    """One EQ chain (10 bands + optional bass + compressor) in series. Returns
    (nodes, links, tail_port). ``prefix`` namespaces the nodes so two chains (L/R) can
    coexist in one graph; the empty prefix reproduces the original mono chain verbatim."""
    nodes = [
        f'{{ type = builtin name = {prefix}eq_band_{i} label = {label} '
        f'control = {{ "Freq" = {freq} "Q" = 1.0 "Gain" = {float(gain)} }} }}'
        for i, (freq, label, gain) in enumerate(zip(BAND_FREQS, _LABELS, gains), start=1)
    ]
    links = [
        f'{{ output = "{prefix}eq_band_{i}:Out" input = "{prefix}eq_band_{i + 1}:In" }}'
        for i in range(1, 10)
    ]
    tail = f"{prefix}eq_band_10:Out"
    if caps and bass > 0:
        drive = round((clamp_pct(bass) / 100.0) * _BASS_MAX_DRIVE, 3)
        nodes.append(
            f'{{ type = ladspa name = {prefix}spice plugin = "{caps}" label = Spice '
            f'control = {{ "lo.f (Hz)" = {_BASS_FREQ} "lo.gain" = {drive} '
            f'"lo.vol (dB)" = 0 "hi.gain" = 0 }} }}'
        )
        links.append(f'{{ output = "{tail}" input = "{prefix}spice:in" }}')
        tail = f"{prefix}spice:out"
    if caps and loudness:
        nodes.append(
            f'{{ type = ladspa name = {prefix}comp plugin = "{caps}" label = Compress '
            f'control = {_COMP} }}'
        )
        links.append(f'{{ output = "{tail}" input = "{prefix}comp:in" }}')
        tail = f"{prefix}comp:out"
    return nodes, links, tail


def _crossfeed_stage(ltail, rtail, intensity):
    """bs2b-style crossfeed: each ear also gets the opposite channel, low-passed +
    delayed + attenuated, summed in a per-ear mixer. Fed from copy nodes (fan-out validated
    on device). Returns (nodes, links, [outL, outR])."""
    g = crossfeed_gain(intensity)
    # Normalise the per-ear mix to a unity sum (direct + cross = 1) so summing correlated
    # content can never exceed 0 dBFS — clip-safe by construction, no makeup needed.
    direct = round(1.0 / (1.0 + g), 3)
    cross = round(g / (1.0 + g), 3)
    lp = (
        f'control = {{ "Freq" = {CROSSFEED_LOWPASS_HZ} "Q" = {CROSSFEED_LOWPASS_Q} }}'
    )
    dly = f'control = {{ "Delay (s)" = {CROSSFEED_DELAY_S} }}'
    mix = f'control = {{ "Gain 1" = {direct} "Gain 2" = {cross} }}'
    nodes = [
        "{ type = builtin name = cf_copyL label = copy }",
        "{ type = builtin name = cf_copyR label = copy }",
        f"{{ type = builtin name = cf_lpL label = bq_lowpass {lp} }}",
        f"{{ type = builtin name = cf_lpR label = bq_lowpass {lp} }}",
        f"{{ type = builtin name = cf_dL label = delay {dly} }}",
        f"{{ type = builtin name = cf_dR label = delay {dly} }}",
        f"{{ type = builtin name = cf_mixL label = mixer {mix} }}",
        f"{{ type = builtin name = cf_mixR label = mixer {mix} }}",
    ]
    links = [
        f'{{ output = "{ltail}" input = "cf_copyL:In" }}',
        f'{{ output = "{rtail}" input = "cf_copyR:In" }}',
        '{ output = "cf_copyL:Out" input = "cf_mixL:In 1" }',
        '{ output = "cf_copyL:Out" input = "cf_lpL:In" }',
        '{ output = "cf_lpL:Out" input = "cf_dL:In" }',
        '{ output = "cf_dL:Out" input = "cf_mixR:In 2" }',
        '{ output = "cf_copyR:Out" input = "cf_mixR:In 1" }',
        '{ output = "cf_copyR:Out" input = "cf_lpR:In" }',
        '{ output = "cf_lpR:Out" input = "cf_dR:In" }',
        '{ output = "cf_dR:Out" input = "cf_mixL:In 2" }',
    ]
    return nodes, links, ["cf_mixL:Out", "cf_mixR:Out"]


def _width_stage(ltail, rtail, width):
    """Mid/side stereo width: M=(L+R)/2, S=(L-R)/2, recombine L'=M+wS, R'=M-wS. The minus
    is an ``invert`` node (no negative mixer gains). w = width_factor: 1.0 is a bit-exact
    passthrough, <1 narrows toward mono, >1 widens. Returns (nodes, links, [outL, outR])."""
    w = width_factor(width)
    half = 'control = { "Gain 1" = 0.5 "Gain 2" = 0.5 }'
    rec = f'control = {{ "Gain 1" = 1.0 "Gain 2" = {w} }}'
    nodes = [
        "{ type = builtin name = w_cL label = copy }",
        "{ type = builtin name = w_cR label = copy }",
        "{ type = builtin name = w_invR label = invert }",
        f"{{ type = builtin name = w_mixM label = mixer {half} }}",
        f"{{ type = builtin name = w_mixS label = mixer {half} }}",
        "{ type = builtin name = w_invS label = invert }",
        f"{{ type = builtin name = w_mixL label = mixer {rec} }}",
        f"{{ type = builtin name = w_mixR label = mixer {rec} }}",
    ]
    links = [
        f'{{ output = "{ltail}" input = "w_cL:In" }}',
        f'{{ output = "{rtail}" input = "w_cR:In" }}',
        '{ output = "w_cL:Out" input = "w_mixM:In 1" }',
        '{ output = "w_cR:Out" input = "w_mixM:In 2" }',
        '{ output = "w_cL:Out" input = "w_mixS:In 1" }',
        '{ output = "w_cR:Out" input = "w_invR:In" }',
        '{ output = "w_invR:Out" input = "w_mixS:In 2" }',
        '{ output = "w_mixM:Out" input = "w_mixL:In 1" }',
        '{ output = "w_mixS:Out" input = "w_mixL:In 2" }',
        '{ output = "w_mixM:Out" input = "w_mixR:In 1" }',
        '{ output = "w_mixS:Out" input = "w_invS:In" }',
        '{ output = "w_invS:Out" input = "w_mixR:In 2" }',
    ]
    return nodes, links, ["w_mixL:Out", "w_mixR:Out"]


def _ports(names):
    return " ".join(f'"{p}"' for p in names)


def _render(nodes, links, sink_name, description, inputs=None, outputs=None):
    nodes_s = "\n".join(f"          {n}" for n in nodes)
    links_s = "\n".join(f"          {link}" for link in links)
    io = ""
    if inputs is not None and outputs is not None:
        io = (
            f'\n        inputs  = [ {_ports(inputs)} ]'
            f'\n        outputs = [ {_ports(outputs)} ]'
        )
    return f"""context.modules = [
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = "{description}"
      media.name       = "{description}"
      filter.graph = {{
        nodes = [
{nodes_s}
        ]
        links = [
{links_s}
        ]{io}
      }}
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props  = {{ node.name = "{description}" node.description = "{description}" node.nick = "{description}" media.class = Audio/Sink priority.session = 2000 }}
      playback.props = {{ node.name = "effect_output.{sink_name}" node.passive = true }}
    }}
  }}
]
"""


def build_chain_config(
    gains,
    sink_name,
    description="Panel de Control",
    bass=0,
    loudness=False,
    caps=None,
    crossfeed=0,
    stereo_width=WIDTH_NEUTRAL,
):
    """Filter-chain conf for the EQ sink. Mono (duplicated onto FL/FR) unless a spatial
    effect is engaged: crossfeed (headphones) or stereo width != neutral (speakers), which
    switch the graph to explicit stereo. crossfeed and stereo_width are route-exclusive by
    construction (the caller passes the neutral value for the route that doesn't apply)."""
    if crossfeed <= 0 and stereo_width == WIDTH_NEUTRAL:
        nodes, links, _tail = _channel_chain(gains, bass, loudness, caps)
        return _render(nodes, links, sink_name, description)

    lnodes, llinks, ltail = _channel_chain(gains, bass, loudness, caps, "l_")
    rnodes, rlinks, rtail = _channel_chain(gains, bass, loudness, caps, "r_")
    if crossfeed > 0:
        snodes, slinks, outs = _crossfeed_stage(ltail, rtail, crossfeed)
    else:
        snodes, slinks, outs = _width_stage(ltail, rtail, stereo_width)
    return _render(
        lnodes + rnodes + snodes,
        llinks + rlinks + slinks,
        sink_name,
        description,
        inputs=["l_eq_band_1:In", "r_eq_band_1:In"],
        outputs=outs,
    )
