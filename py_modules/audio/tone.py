"""Pink-noise reference tone for auditioning the EQ without launching a game. Pink noise
(equal energy per octave) is the standard broadband reference for judging tonal balance.
Generated (Voss-McCartney) so it works on any device without shipping an audio asset."""
import random
import struct
import wave

_ROWS = 16  # octave-spaced white sources summed → pink spectrum


def pink_samples(n, seed=1):
    """`n` mono pink-noise samples in [-1, 1], normalized to ~0.6 peak for headroom.
    Deterministic for a given seed."""
    rng = random.Random(seed)
    values = [rng.uniform(-1, 1) for _ in range(_ROWS)]
    total = sum(values)
    out = []
    peak = 0.0
    for i in range(1, n + 1):
        row = (i & -i).bit_length() - 1  # index of the lowest set bit
        if 0 <= row < _ROWS:
            total -= values[row]
            values[row] = rng.uniform(-1, 1)
            total += values[row]
        out.append(total)
        if abs(total) > peak:
            peak = abs(total)
    scale = (0.6 / peak) if peak else 0.0
    return [s * scale for s in out]


def write_wav(path, samples, rate=48000):
    """Write mono `samples` as a 16-bit stereo WAV (duplicated to both channels)."""
    frames = bytearray()
    for s in samples:
        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack("<hh", v, v)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
