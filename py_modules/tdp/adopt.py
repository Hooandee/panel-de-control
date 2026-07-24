"""External-TDP adoption debounce.

The firmware PL1 read back can differ from what we wrote either because a real
external tool (HHD / Steam) changed it — which we WANT to adopt so a later
re-apply doesn't stomp the user's deliberate change — or because the firmware
spiked the rail for a moment on its own (seen on newer ASUS kernels under load).
Adopting a one-shot spike would turn a transient into a permanent setpoint (the
slider "jumps" and stays). So require the divergent value to persist across two
consecutive reads before adopting: a real change persists, a spike does not.
"""
from __future__ import annotations


def should_adopt_external(applied, last_written, pending, threshold):
    """Decide whether to adopt ``applied`` as our setpoint.

    Returns ``(adopt, next_pending)``: ``adopt`` is True only when ``applied``
    diverges from ``last_written`` by at least ``threshold`` AND equals the
    candidate seen on the previous read (``pending``). ``next_pending`` is the
    candidate to carry into the next read (None once cleared/adopted).
    """
    if applied is None or last_written is None:
        return (False, None)
    if abs(int(applied) - int(last_written)) < threshold:
        # Back within range → not an external change; drop any armed candidate.
        return (False, None)
    a = int(applied)
    if pending is not None and int(pending) == a:
        # Same divergent value twice in a row → a real, settled external change.
        return (True, None)
    # First sighting (or the value moved) → arm and wait for confirmation.
    return (False, a)
