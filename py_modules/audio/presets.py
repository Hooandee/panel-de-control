"""Curated EQ presets. Generic use-presets apply to any device; ``device_tuned`` is the
per-machine internal-speaker correction (the hero), only meaningful on the speaker route —
headphones get no speaker correction. The device curves here are a starting point, refined
per model with measured/community data (see the design doc, sources tracked for attribution)."""

from audio.const import clamp_gain, compute_preamp

# Generic use-presets: gains in dB per band [32, 64, 125, 250, 500, 1k, 2k, 4k, 8k, 16k].
GENERIC = {
    "flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "voices": [-2, -1, 0, 1, 2, 3, 3, 2, 1, 0],
    "bass": [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "cinema": [4, 3, 1, 0, -1, 0, 1, 2, 3, 2],
    "music": [3, 2, 0, -1, -1, 0, 1, 2, 2, 1],
}

_GENERIC_ORDER = ["flat", "voices", "bass", "cinema", "music"]

# Per-device internal-speaker correction (bass lift + presence + air). Provisional; refined
# on-device per model. Device keys match device_registry.
DEVICE = {
    "legion_go": {"device_tuned": [5, 4, 2, 0, -1, 0, 1, 3, 4, 3]},
    "legion_go_2": {"device_tuned": [5, 4, 2, 0, -1, 0, 1, 3, 4, 3]},
}


def _setting(preset_id, gains):
    g = [clamp_gain(x) for x in gains]
    return {"preset": preset_id, "gains": g, "preamp": compute_preamp(g)}


def resolve_preset(device_key, preset_id, route):
    if preset_id == "device_tuned":
        if route != "speaker":
            return _setting("device_tuned", [0.0] * 10)
        gains = DEVICE.get(device_key, {}).get("device_tuned", GENERIC["flat"])
        return _setting("device_tuned", gains)
    return _setting(preset_id, GENERIC.get(preset_id, GENERIC["flat"]))


def list_presets(device_key):
    out = []
    if "device_tuned" in DEVICE.get(device_key, {}):
        out.append({"id": "device_tuned"})
    out.extend({"id": pid} for pid in _GENERIC_ORDER)
    return out
