"""Builds the PipeWire filter-chain config text for the EQ sink: 10 biquad bands
(lowshelf at the bottom, highshelf at the top, peaking in between) chained in series.
Pure string building — writing/loading the conf and restarting the service live in the
PipeWire lifecycle module. Pre-amp is applied as the sink volume, not a graph node."""

from audio.const import BAND_FREQS

_LABELS = ["bq_lowshelf"] + ["bq_peaking"] * 8 + ["bq_highshelf"]


def build_chain_config(gains, sink_name):
    nodes = []
    for i, (freq, label, gain) in enumerate(zip(BAND_FREQS, _LABELS, gains), start=1):
        nodes.append(
            f'          {{ type = builtin name = eq_band_{i} label = {label} '
            f'control = {{ "Freq" = {freq} "Q" = 1.0 "Gain" = {float(gain)} }} }}'
        )
    links = [
        f'          {{ output = "eq_band_{i}:Out" input = "eq_band_{i + 1}:In" }}'
        for i in range(1, 10)
    ]
    nodes_s = "\n".join(nodes)
    links_s = "\n".join(links)
    return f"""context.modules = [
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = "PdC EQ"
      media.name       = "PdC EQ"
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
      capture.props  = {{ node.name = "effect_input.{sink_name}" node.description = "Panel de Control" media.class = Audio/Sink }}
      playback.props = {{ node.name = "effect_output.{sink_name}" node.passive = true }}
    }}
  }}
]
"""
