"""Generic fan-curve presets (device-agnostic for now).

Each preset is 8 ``(temp_celsius, pwm_0_255)`` points. Resolution runs them
through ``sanitize_curve`` so monotonicity and the safe max-temp PWM floor are
always guaranteed regardless of the raw values here.
"""
from fans.control import sanitize_curve

PRESETS: dict[str, list[tuple[int, int]]] = {
    "silent": [(40, 0), (50, 0), (60, 20), (70, 45), (80, 85), (85, 130), (90, 185), (95, 235)],
    "balanced": [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)],
    "performance": [(40, 45), (45, 75), (50, 105), (60, 145), (70, 185), (80, 220), (85, 245), (90, 255)],
}

_DEFAULT = "balanced"


def resolve(preset_id: str) -> list[tuple[int, int]]:
    """Return the sanitized 8-point curve for ``preset_id`` (falls back to balanced)."""
    raw = PRESETS.get(preset_id, PRESETS[_DEFAULT])
    return sanitize_curve(raw, pwm_max=255, floor_pwm=0)


# Preset curves are static — resolve once at import (the sanitize pass is constant
# work otherwise repeated on every get_fan_curve_state call).
RESOLVED: dict[str, list[tuple[int, int]]] = {pid: resolve(pid) for pid in PRESETS}
