"""A short, pleasant reference tone for auditioning the EQ when nothing else is playing.
A gentle plucked C-major arpeggio (sines with a soft decay + one warm harmonic) that
spans bass → treble so tone changes are audible. Generated (no shipped asset), musical —
not the harsh noise a spectrum test would give."""
import math
import struct
import wave

# C major spread across the range the EQ shapes: C3, G3, C4, E4, G4, C5.
_NOTES = [130.81, 196.00, 261.63, 329.63, 392.00, 523.25]
_STEP = 0.28   # seconds between plucks
_DECAY = 1.4   # seconds for a note to fade


def arpeggio_samples(rate=48000, seconds=3.2):
    n = int(rate * seconds)
    out = [0.0] * n
    for k, freq in enumerate(_NOTES):
        start = int(k * _STEP * rate)
        for i in range(start, n):
            t = (i - start) / rate
            env = math.exp(-t / _DECAY)
            if env < 0.001:
                break
            # fundamental + a quieter octave for warmth
            s = math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * 2 * freq * t)
            out[i] += env * s
    peak = max((abs(v) for v in out), default=0.0)
    scale = (0.5 / peak) if peak else 0.0
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
