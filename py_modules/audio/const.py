"""Audio EQ constants and pure helpers shared by the store, presets and the config
builder. A graphic EQ: 10 fixed frequencies, each band a gain in dB."""

BAND_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
GAIN_MIN = -12.0
GAIN_MAX = 12.0
ROUTES = ["speaker", "headphone"]
BALANCE_MIN = -100
BALANCE_MAX = 100


def clamp_gain(value):
    try:
        return max(GAIN_MIN, min(GAIN_MAX, float(value)))
    except (TypeError, ValueError):
        return 0.0


def clamp_balance(value):
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if v != v:
        return 0
    return int(max(BALANCE_MIN, min(BALANCE_MAX, v)))


def balance_channels(balance):
    """Balance → (left%, right%) for the downstream sink. Only the far side is attenuated so
    panning never raises loudness."""
    b = clamp_balance(balance)
    left = 100 if b <= 0 else 100 - b
    right = 100 if b >= 0 else 100 + b
    return left, right


def compute_preamp(gains):
    """Negative headroom so a boosted band never clips: -(highest positive gain). Only
    positive boosts eat headroom; a cut needs none."""
    peak = max([0.0] + [clamp_gain(g) for g in gains])
    return -peak
