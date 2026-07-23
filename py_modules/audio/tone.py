import math
import os
import random
import struct
import wave

_BEAT = 0.5
_BEATS = 8
_PEAK = 0.5
CACHE_TAG = "v2"


def _canvas(rate):
    n = int(rate * _BEAT * _BEATS)
    out = [0.0] * n

    def stamp(start, length, amp, fn):
        a, b = int(start * rate), min(n, int((start + length) * rate))
        for i in range(a, b):
            out[i] += amp * fn((i - a) / rate)

    return out, stamp


def _envelope(t, length, atk, rel):
    rise = t / atk if atk > 0 else 1.0
    fall = (length - t) / rel if rel > 0 else 1.0
    return max(0.0, min(1.0, rise, fall))


def _partials(freq, length, parts, atk=0.02, rel=0.1):
    def fn(t):
        e = _envelope(t, length, atk, rel)
        return e * sum(a * math.sin(2 * math.pi * freq * m * t) for m, a in parts)
    return fn


def _kick(t):
    freq = 55 + 70 * math.exp(-t * 30)
    return math.sin(2 * math.pi * freq * t) * math.exp(-t * 8)


def _finish(out, rate):
    peak = max((abs(v) for v in out), default=0.0)
    scale = (_PEAK / peak) if peak else 0.0
    out = [v * scale for v in out]
    edge = min(len(out) // 4, int(0.03 * rate) or 1)
    for i in range(edge):
        f = i / edge
        out[i] *= f
        out[-1 - i] *= f
    return out


def _bass(rate=48000):
    out, stamp = _canvas(rate)
    line = [98.00, 98.00, 146.83, 130.81]
    for b in range(_BEATS):
        stamp(b * _BEAT, 0.4, 1.0, _kick)
    for k, freq in enumerate(line):
        note = _partials(freq, 2 * _BEAT, [(1, 1.0), (2, 0.4)], atk=0.01, rel=0.15)
        stamp(k * 2 * _BEAT, 2 * _BEAT, 0.7, note)
    return _finish(out, rate)


def _voice(rate=48000):
    out, stamp = _canvas(rate)
    notes = [329.63, 392.00, 440.00, 392.00, 349.23, 392.00, 329.63, 293.66]
    for k, freq in enumerate(notes):
        note = _partials(freq, _BEAT, [(1, 1.0), (2, 0.5), (3, 0.25)], atk=0.03, rel=0.12)
        stamp(k * _BEAT, _BEAT, 0.6, note)
    return _finish(out, rate)


def _treble(rate=48000):
    out, stamp = _canvas(rate)
    rng = random.Random(7)
    bells = [2093.0, 2637.0, 3136.0, 2637.0]

    def hat(t):
        return rng.uniform(-1, 1) * math.exp(-t * 60)

    for b in range(_BEATS):
        stamp(b * _BEAT, 0.05, 0.35, hat)
        stamp((b + 0.5) * _BEAT, 0.04, 0.22, hat)
    for k, freq in enumerate(bells):
        note = _partials(freq, 1.0, [(1, 1.0), (2, 0.3)], atk=0.005, rel=0.5)
        stamp(k * 2 * _BEAT, 1.0, 0.3, note)
    return _finish(out, rate)


def _full(rate=48000):
    out, stamp = _canvas(rate)
    rng = random.Random(42)
    bass = [98.00, 98.00, 146.83, 130.81]
    lead = [392.00, 493.88, 587.33, 493.88, 440.00, 392.00]

    def hat(t):
        return rng.uniform(-1, 1) * math.exp(-t * 70)

    for b in range(_BEATS):
        stamp(b * _BEAT, 0.35, 0.8, _kick)
        stamp((b + 0.5) * _BEAT, 0.05, 0.18, hat)
    for k, freq in enumerate(bass):
        stamp(k * 2 * _BEAT, 2 * _BEAT, 0.45, _partials(freq, 2 * _BEAT, [(1, 1.0), (2, 0.4)], rel=0.15))
    for k, freq in enumerate(lead):
        stamp((k + 1) * _BEAT, _BEAT, 0.3, _partials(freq, _BEAT, [(1, 1.0), (2, 0.4), (3, 0.2)], atk=0.02, rel=0.1))
    return _finish(out, rate)


SAMPLES = {"bass": _bass, "voice": _voice, "treble": _treble, "full": _full}


def sample_ids():
    return list(SAMPLES)


def render(sample_id, rate=48000):
    return SAMPLES.get(sample_id, _full)(rate)


def write_wav(path, samples, rate=48000):
    frames = bytearray()
    for s in samples:
        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack("<hh", v, v)
    tmp = f"{path}.tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    os.replace(tmp, path)
