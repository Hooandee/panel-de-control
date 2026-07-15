"""Curated EQ presets. Generic use-presets apply to any device; ``device_tuned`` is the
per-machine internal-speaker correction (the hero), only meaningful on the speaker route —
headphones get no speaker correction. The device curves here are a starting point, refined
per model with measured/community data."""

from audio.const import clamp_gain, compute_preamp

# Generic use-presets: gains in dB per band [32, 64, 125, 250, 500, 1k, 2k, 4k, 8k, 16k].
GENERIC = {
    "flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    # Dialogue/footsteps: cut boom, lift presence — clear voices without the harsh top.
    "voices": [-4, -3, -1, 0, 1, 2, 3, 2, 0, -1],
    # Body/warmth from upper bass (tiny drivers can't do deep sub, so 32/64 stay modest).
    "bass": [2, 4, 5, 3, 1, 0, 0, 0, 0, 1],
    # Cinematic V-shape: fuller lows + airy highs, scooped mids.
    "cinema": [3, 4, 3, 1, -2, -3, -1, 1, 3, 3],
    # Gentle smile for music.
    "music": [2, 3, 2, 0, -1, -1, 0, 1, 3, 2],
}

# Per-device internal-speaker correction. The proven fix for small/thin laptop-class
# speakers (EasyEffects laptop-speaker method): add upper-bass body (~125 Hz) and CUT the
# harsh mid presence (~800 Hz–2 kHz) that makes them sound tinny/boxy, leaving treble
# roughly flat. Modelled on a documented Lenovo ThinkPad small-speaker preset — the closest
# published analog; refine with a real Legion measurement when available.
DEVICE = {
    "legion_go": {"device_tuned": [0, 0, 3, 1, -1, -4, -3, -2, 0, 1]},
    "legion_go_2": {"device_tuned": [0, 0, 3, 1, -1, -4, -3, -2, 0, 1]},
}

_GENERIC_CORRECTION = [0, 1, 2, 1, -1, -2, -2, -1, 0, 1]


def is_tuned(device_key):
    return "device_tuned" in DEVICE.get(device_key, {})


def _setting(preset_id, gains):
    g = [clamp_gain(x) for x in gains]
    return {"preset": preset_id, "gains": g, "preamp": compute_preamp(g)}


def resolve_preset(device_key, preset_id, route):
    if preset_id == "device_tuned":
        if route != "speaker":
            return _setting("device_tuned", [0.0] * 10)
        gains = DEVICE.get(device_key, {}).get("device_tuned", _GENERIC_CORRECTION)
        return _setting("device_tuned", gains)
    return _setting(preset_id, GENERIC.get(preset_id, GENERIC["flat"]))


def list_presets(device_key):
    out = [{"id": "device_tuned", "tuned": is_tuned(device_key)}]
    out.extend({"id": pid} for pid in GENERIC)
    return out
