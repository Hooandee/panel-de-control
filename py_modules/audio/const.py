"""Audio EQ constants and pure helpers shared by the store, presets and the config
builder. A graphic EQ: 10 fixed frequencies, each band a gain in dB."""

BAND_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
GAIN_MIN = -12.0
GAIN_MAX = 12.0
ROUTES = ["speaker", "headphone"]

# Stereo width (speaker route): a 0-100 dial where 50 is neutral. Maps to a mid/side
# factor w = pct/50, so 0 = mono, 50 = untouched, 100 = 2x wide.
WIDTH_NEUTRAL = 50

# Crossfeed (headphone route): a 0-100 dial. Each ear receives the opposite channel,
# low-passed + delayed (bs2b-style), so headphones sound less "inside the head".
CROSSFEED_LOWPASS_HZ = 700
CROSSFEED_LOWPASS_Q = 0.7
CROSSFEED_DELAY_S = 0.0003  # ~0.3 ms inter-aural delay
_CROSSFEED_MAX_GAIN = 0.6   # cross-mix level at full intensity


def clamp_gain(value):
    try:
        return max(GAIN_MIN, min(GAIN_MAX, float(value)))
    except (TypeError, ValueError):
        return 0.0


def clamp_pct(value, default=0):
    """A 0-100 integer dial (crossfeed intensity, stereo width). Invalid/absent input
    falls back to ``default`` (e.g. WIDTH_NEUTRAL for a width dial, 0 for an off-at-zero one)."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def width_factor(pct):
    """Mid/side width multiplier for a 0-100 dial: 0->0 (mono), 50->1 (neutral), 100->2."""
    return round(clamp_pct(pct) / float(WIDTH_NEUTRAL), 3)


def crossfeed_gain(pct):
    """Cross-mix level (0..0.6) for a 0-100 crossfeed dial. 0 = no crossfeed."""
    return round((clamp_pct(pct) / 100.0) * _CROSSFEED_MAX_GAIN, 3)


def compute_preamp(gains):
    """Negative headroom so a boosted band never clips: -(highest positive gain). Only
    positive boosts eat headroom; a cut needs none."""
    peak = max([0.0] + [clamp_gain(g) for g in gains])
    return -peak
