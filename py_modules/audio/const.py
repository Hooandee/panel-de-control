"""Audio EQ constants and pure helpers shared by the store, presets and the config
builder. A graphic EQ: 10 fixed frequencies, each band a gain in dB."""

BAND_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
GAIN_MIN = -12.0
GAIN_MAX = 12.0
ROUTES = ["speaker", "headphone"]


def clamp_gain(value):
    try:
        return max(GAIN_MIN, min(GAIN_MAX, float(value)))
    except (TypeError, ValueError):
        return 0.0


def compute_preamp(gains):
    """Negative headroom so a boosted band never clips: -(highest positive gain). Only
    positive boosts eat headroom; a cut needs none."""
    peak = max([0.0] + [clamp_gain(g) for g in gains])
    return -peak
