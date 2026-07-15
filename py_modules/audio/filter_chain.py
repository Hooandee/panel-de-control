"""Builds the PipeWire filter-chain config text for the EQ sink: 10 biquad bands
(lowshelf at the bottom, highshelf at the top, peaking in between) in series, optionally
followed by a CAPS Spice bass enhancer. Pure string building — writing/loading the conf
and restarting the service live in the PipeWire lifecycle module."""

from audio.const import BAND_FREQS

_LABELS = ["bq_lowshelf"] + ["bq_peaking"] * 8 + ["bq_highshelf"]

_CAPS = "/usr/lib/ladspa/caps.so"
_BASS_FREQ = 130  # Hz — the low-mid body small handheld speakers can actually reproduce
_BASS_MAX_DRIVE = 1.0  # lo.gain at bass=100 (harmonic drive); tuned by ear on-device

# Mono Spice (not SpiceX2) so it duplicates per channel like the mono biquads.
_BASS_LABEL = "Spice"


def _band_nodes(gains):
    return [
        f'          {{ type = builtin name = eq_band_{i} label = {label} '
        f'control = {{ "Freq" = {freq} "Q" = 1.0 "Gain" = {float(gain)} }} }}'
        for i, (freq, label, gain) in enumerate(zip(BAND_FREQS, _LABELS, gains), start=1)
    ]


def build_chain_config(gains, sink_name, description="Panel de Control", bass=0):
    nodes = _band_nodes(gains)
    links = [
        f'          {{ output = "eq_band_{i}:Out" input = "eq_band_{i + 1}:In" }}'
        for i in range(1, 10)
    ]
    if bass > 0:
        drive = round((max(0, min(100, bass)) / 100.0) * _BASS_MAX_DRIVE, 3)
        nodes.append(
            f'          {{ type = ladspa name = spice plugin = "{_CAPS}" label = {_BASS_LABEL} '
            f'control = {{ "lo.f (Hz)" = {_BASS_FREQ} "lo.gain" = {drive} '
            f'"lo.vol (dB)" = 0 "hi.gain" = 0 }} }}'
        )
        links.append('          { output = "eq_band_10:Out" input = "spice:In" }')
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
      capture.props  = {{ node.name = "effect_input.{sink_name}" node.description = "{description}" media.class = Audio/Sink priority.session = 2000 }}
      playback.props = {{ node.name = "effect_output.{sink_name}" node.passive = true }}
    }}
  }}
]
"""
