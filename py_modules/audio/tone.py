"""A short, characteristic reference loop for auditioning the EQ — a little beat with a
kick (exercises bass), hi-hats (treble) and a sawtooth bass + lead (rich harmonics across
the mids), so preset/tone changes are clearly audible. Generated (no shipped asset),
musical, and broadband — unlike a pure-sine arpeggio whose energy sits only on a few notes."""
import math
import random
import struct
import wave

_BEAT = 0.42          # ~143 BPM — snappy
_BEATS = 8            # ≈ 3.4 s loop
_BASS = [65.41, 65.41, 98.00, 82.41]                       # C2 C2 G2 E2 (one per 2 beats)
_LEAD = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63]   # C E G C G E


def _saw(freq):
    return lambda t: (2.0 * (freq * t - math.floor(0.5 + freq * t))) * math.exp(-t * 3)


def loop_samples(rate=48000):
    n = int(rate * _BEAT * _BEATS)
    out = [0.0] * n
    rng = random.Random(42)  # seeded → deterministic hi-hat noise

    def stamp(start, length, amp, fn):
        a, b = int(start * rate), min(n, int((start + length) * rate))
        for i in range(a, b):
            out[i] += amp * fn((i - a) / rate)

    def kick(t):
        freq = 45 + 90 * math.exp(-t * 32)   # pitch drop = punch
        return math.sin(2 * math.pi * freq * t) * math.exp(-t * 9)

    def hat(t):
        return rng.uniform(-1, 1) * math.exp(-t * 90)   # bright noise tick

    for b in range(_BEATS):
        stamp(b * _BEAT, 0.25, 0.9, kick)
        stamp((b + 0.5) * _BEAT, 0.08, 0.35, hat)
    for k, freq in enumerate(_BASS):
        stamp(k * 2 * _BEAT, 2 * _BEAT, 0.5, _saw(freq))
    for k, freq in enumerate(_LEAD):
        stamp((k + 1) * _BEAT, _BEAT, 0.28, _saw(freq))

    peak = max((abs(v) for v in out), default=0.0)
    scale = (0.6 / peak) if peak else 0.0
    return [v * scale for v in out]


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
