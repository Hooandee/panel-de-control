"""Suggestion brain — turn a game's observed temperature histogram into a
recommended fan curve fit to the band the game actually runs in.

Pure functions, no I/O. The honest contract: we only fit the *active ramp* to the
real temperature band — the dial is a preference (quieter ↔ cooler), NOT a promise
of a target temperature. Degrades via ``enough_data`` when there isn't enough real
data behind a recommendation.
"""

from fans.control import _interp, sanitize_curve

# Gate: don't suggest until we've seen real, varied usage.
_MIN_SECONDS = 1800            # ~30 min of in-game dwell
MIN_MINUTES = _MIN_SECONDS // 60   # learning-progress target (minutes), for the UI
_MIN_SPREAD = 8                # P90-P10 °C — refuse to fit a flat (idle-only) band

# The curve's temp anchors (mirror the presets so an applied suggestion edits
# cleanly in the curve graph).
_ANCHORS = (40, 50, 60, 70, 80, 85, 90, 95)

# Balanced duty (%) control points, placed on the observed band percentiles.
# (temp_source, duty_percent) — temps are filled from the band at runtime.
_BALANCED_DUTY = {"floor": 0, "typical": 30, "high": 55, "peak": 80}

# How much the dial shifts duty for the cooler / quieter variants (percentage pts).
_DIAL_BIAS = 18


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _percentile(hist: dict, q: float):
    """Seconds-weighted percentile temperature of *hist* ({bin: seconds})."""
    if not hist:
        return None
    items = sorted(hist.items())
    total = sum(s for _, s in items)
    if total <= 0:
        return None
    target = q * total
    cum = 0.0
    for temp, seconds in items:
        cum += seconds
        if cum >= target:
            return temp
    return items[-1][0]


def enough_data(hist: dict):
    """Return ``(ok, reason)``. reason ∈ {ok, no_data, too_few, flat}."""
    total = sum(hist.values()) if hist else 0.0
    if total <= 0:
        return (False, "no_data")
    if total < _MIN_SECONDS:
        return (False, "too_few")
    p10, p90 = _percentile(hist, 0.10), _percentile(hist, 0.90)
    if p90 - p10 < _MIN_SPREAD:
        return (False, "flat")
    return (True, "ok")


def band(hist: dict) -> dict:
    """The game's thermal band as percentiles (None-safe defaults if empty)."""
    return {
        "floor": _percentile(hist, 0.10) or 50,
        "typical": _percentile(hist, 0.50) or 65,
        "high": _percentile(hist, 0.90) or 80,
        "peak": _percentile(hist, 0.98) or 90,
    }


def _curve(b: dict, bias: int):
    """Build a sanitized 8-point temp→pwm curve for the band, shifted by *bias* %."""
    control = [(b[k], _clamp(duty + bias, 0, 100)) for k, duty in _BALANCED_DUTY.items()]
    control.append((100, 100))
    pts = []
    for anchor in _ANCHORS:
        pct = _clamp(_interp(control, anchor, round_int=False), 0, 100)
        pts.append((anchor, round(pct / 100 * 255)))
    return sanitize_curve(pts, pwm_max=255, floor_pwm=0)


def curve_changed(old, new, tol_pwm: int = 8) -> bool:
    """Whether *new* differs from *old* enough to be worth re-applying (anti-churn).

    Used by the periodic re-apply: re-fitting the learned curve every ~30 min
    would otherwise churn the hardware (and eMMC) on cosmetic drift. Returns True
    when any control point's pwm moves by more than *tol_pwm* (default 8/255 ≈ 3 %),
    or when there's no vigente curve at all (a first apply must always go through).
    """
    if not old:
        return True
    if len(old) != len(new):
        return True
    for (_t_old, pwm_old), (_t_new, pwm_new) in zip(old, new):
        if abs(pwm_new - pwm_old) > tol_pwm:
            return True
    return False


def suggest_curves(b: dict) -> dict:
    """Return {quiet, balanced, cool} 8-point temp→pwm curves for the band."""
    return {
        "quiet": _curve(b, -_DIAL_BIAS),
        "balanced": _curve(b, 0),
        "cool": _curve(b, +_DIAL_BIAS),
    }


def biased_curve(curves: dict, bias: int) -> list:
    """Blend the {quiet, balanced, cool} curves by a silence↔cool *bias* (-100..100).

    bias 0 = balanced, -100 = fully quiet, +100 = fully cool. Mirrors the frontend
    `interpolateCurves` so the driven hardware curve matches the card's preview. Same
    temp anchors across the three curves → interpolate pwm point-wise. Result is
    sanitized so the hot-point safety floor holds regardless of the bias.
    """
    d = _clamp(bias, -100, 100) / 100.0
    balanced = curves["balanced"]
    other = curves["quiet"] if d < 0 else curves["cool"]
    frac = abs(d)
    pts = []
    for (temp, pwm_b), (_t, pwm_o) in zip(balanced, other):
        pts.append((temp, round(pwm_b + (pwm_o - pwm_b) * frac)))
    return sanitize_curve(pts, pwm_max=255, floor_pwm=0)
