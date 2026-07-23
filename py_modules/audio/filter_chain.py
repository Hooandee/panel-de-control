"""Builds the PipeWire filter-chain config text for the EQ sink: 10 biquad bands
(lowshelf at the bottom, highshelf at the top, peaking in between) in series, optionally
followed by a CAPS Spice bass enhancer. Pure string building — writing/loading the conf
and restarting the service live in the PipeWire lifecycle module."""

from audio.const import BAND_FREQS

_LABELS = ["bq_lowshelf"] + ["bq_peaking"] * 8 + ["bq_highshelf"]

_BASS_FREQ = 130
_BASS_MAX_DRIVE = 1.0

_COMP = '{ "threshold" = -18 "strength" = 0.6 "attack" = 20 "release" = 200 "gain (dB)" = 6 }'

# Mono CAPS effects (not the X2 stereo variants) so they duplicate per channel like the
# mono biquads. Their audio ports are lowercase in/out (LADSPA), not the builtin In/Out.


def _band_nodes(gains):
    return [
        f'          {{ type = builtin name = eq_band_{i} label = {label} '
        f'control = {{ "Freq" = {freq} "Q" = 1.0 "Gain" = {float(gain)} }} }}'
        for i, (freq, label, gain) in enumerate(zip(BAND_FREQS, _LABELS, gains), start=1)
    ]


def build_chain_config(gains, sink_name, description="Panel de Control", bass=0, loudness=False, caps=None):
    nodes = _band_nodes(gains)
    links = [
        f'          {{ output = "eq_band_{i}:Out" input = "eq_band_{i + 1}:In" }}'
        for i in range(1, 10)
    ]
    tail = "eq_band_10:Out"  # the current graph output; extra effects chain onto it in order
    # Bass and loudness are CAPS (LADSPA) effects; without caps.so on this system they're
    # dropped rather than pointing the graph at a missing plugin (which fails the whole chain).
    if caps and bass > 0:
        drive = round((max(0, min(100, bass)) / 100.0) * _BASS_MAX_DRIVE, 3)
        nodes.append(
            f'          {{ type = ladspa name = spice plugin = "{caps}" label = Spice '
            f'control = {{ "lo.f (Hz)" = {_BASS_FREQ} "lo.gain" = {drive} '
            f'"lo.vol (dB)" = 0 "hi.gain" = 0 }} }}'
        )
        links.append(f'          {{ output = "{tail}" input = "spice:in" }}')
        tail = "spice:out"
    if caps and loudness:
        nodes.append(
            f'          {{ type = ladspa name = comp plugin = "{caps}" label = Compress '
            f'control = {_COMP} }}'
        )
        links.append(f'          {{ output = "{tail}" input = "comp:in" }}')
        tail = "comp:out"
    nodes_s = "\n".join(nodes)
    links_s = "\n".join(links)
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
        ]
      }}
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props  = {{ node.name = "{description}" node.description = "{description}" node.nick = "{description}" media.class = Audio/Sink priority.session = 2000 }}
      playback.props = {{ node.name = "effect_output.{sink_name}" node.passive = true }}
    }}
  }}
]
"""
