"""PlayStation 5 thermal guard: past the threshold the fan target drops to its coolest
value (the firmware then spins the fan as hard as it needs) and, when enabled, the
console beeps once. Both release after the APU cools by HYSTERESIS_C, so a reading
that hovers at the threshold does not toggle the fan."""
from dataclasses import dataclass

THRESHOLD_MIN_C = 80
THRESHOLD_MAX_C = 100
THRESHOLD_DEFAULT_C = 95
HYSTERESIS_C = 10


def clamp_threshold(celsius) -> int:
    return max(THRESHOLD_MIN_C, min(THRESHOLD_MAX_C, int(celsius)))


@dataclass
class GuardStep:
    engage: bool = False
    release: bool = False
    beep: bool = False


class ThermalGuard:
    def __init__(self) -> None:
        self.active = False
        self.alarmed = False
        self.last_celsius: float | None = None

    def step(self, celsius: float | None, *, threshold: int, guard: bool, alarm: bool) -> GuardStep:
        self.last_celsius = celsius
        out = GuardStep()
        if celsius is None:
            return out
        hot = celsius >= threshold
        cooled = celsius <= threshold - HYSTERESIS_C
        if guard and hot and not self.active:
            self.active = out.engage = True
        elif self.active and (cooled or not guard):
            self.active = False
            out.release = True
        if alarm and hot and not self.alarmed:
            self.alarmed = out.beep = True
        elif self.alarmed and (cooled or not alarm):
            self.alarmed = False
        return out
