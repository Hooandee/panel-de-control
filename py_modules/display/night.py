"""Night mode: a scheduled warm shift on top of the calibration. Pure schedule logic
here; the store persists it and main.py runs the clock."""

_DAY = 24 * 60
STEP = 15  # times snap to a 15-minute grid


def clamp_minute(value):
    """A minute-of-day in [0, 1439], snapped to the 15-min grid, robust to junk."""
    try:
        m = int(value)
    except (TypeError, ValueError):
        return 0
    m = max(0, min(_DAY - 1, m))
    return (m // STEP) * STEP


def is_night_active(now_min, enabled, schedule_enabled, start, end):
    """Whether the warm shift should be applied now. Off unless `enabled`. When enabled:
    always on, unless `schedule_enabled`, in which case only inside the [start, end)
    window (wrapping past midnight). A zero-length window (start == end) is never active."""
    if not enabled:
        return False
    if not schedule_enabled:
        return True
    if start == end:
        return False
    if start < end:
        return start <= now_min < end
    return now_min >= start or now_min < end  # window wraps midnight
