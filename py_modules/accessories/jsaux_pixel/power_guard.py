"""Current limits for the panel's LEDs.

The ceilings mirror the official app: on a strong USB root port the brightness slider tops out at
PWM 80, on any other port at PWM 30. On top of that every frame's average light output is held
under a budget, so bright full-screen art is dimmed instead of drawing peak current.
"""

from . import codec
from .gif import Frame

STRONG_PWM = 80
WEAK_PWM = 30
LIGHT_BUDGET = 0.35
_BLOCKED_TEST_PATTERNS = frozenset({0x04, 0xFF})


def pwm_for(percent: int, strong: bool) -> int:
    ceiling = STRONG_PWM if strong else WEAK_PWM
    percent = max(0, min(100, int(percent)))
    if percent == 0:
        return 0
    return max(1, round(ceiling * percent / 100))


def frame_load(palette: list[tuple[int, int, int]], frame: Frame) -> float:
    weights = [sum(rgb) / (3 * 255) for rgb in palette]
    counts = [0] * len(palette)
    for index in frame.pixels:
        if index < len(counts):
            counts[index] += 1
    return sum(w * c for w, c in zip(weights, counts)) / len(frame.pixels)


def limit_palette(palette: list[tuple[int, int, int]], frames: list[Frame]) -> list[tuple[int, int, int]]:
    peak = max(frame_load(palette, frame) for frame in frames)
    if peak <= LIGHT_BUDGET:
        return list(palette)
    scale = LIGHT_BUDGET / peak
    return [tuple(int(channel * scale) for channel in rgb) for rgb in palette]


def allowed(frame: bytes) -> bool:
    command, payload = frame[3], frame[6:-2]
    if command == codec.Cmd.TEST:
        return payload[:1] not in {bytes((p,)) for p in _BLOCKED_TEST_PATTERNS}
    if command == codec.Cmd.BRIGHTNESS:
        return payload[:1] != b"" and payload[0] <= STRONG_PWM
    return True
