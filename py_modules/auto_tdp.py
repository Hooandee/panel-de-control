"""Auto-TDP control law — GPU-utilisation driven, dead-band + temporal hysteresis.

Converges on the "knee" (the least sustained PL1 that keeps the GPU just below
saturation) and HOLDS there. Deliberately does NOT use real watts or boost: when a
game is power-limited the draw simply follows PL1 (it eats the whole budget across
CPU+GPU), so EVERY draw-derived signal — boost magnitude, boost frequency, watts
headroom — is confounded and can't tell "has margin" from "needs it". Measured
on-device (ROG Ally): pl1=35 (cap), draw=35 W (pinned), GPU=80% stable → the
watts/boost model saw "no headroom" and held at max forever, yet 80% GPU means
there IS margin. GPU utilisation is the only honest "can it go lower?" signal.

Signals kept: GPU% only. Watts/boost are dropped from the control decision.

Three states:
  - UP    (fast, wins over all): a recent GPU peak (last few samples) >= _UP_GPU.
    Saturated = the game needs more NOW → +up_step. Over-giving briefly is cheap;
    starving the GPU tanks FPS.
  - HOLD:  mean GPU in the dead-band (_DOWN_GPU..._UP_GPU) = the knee → stay put.
    The dead-band + the temporal gate below are exactly what the old GPU-only
    tracker lacked → no sawtooth.
  - DOWN  (agile, gated): mean GPU SUSTAINED at/below _DOWN_GPU for _SLACK_HOLD
    ticks → step down, PROPORTIONAL to how far the GPU is below the knee (a light
    scene at 55% drops fast; 85% just below the knee drops by one), bounded to
    [down_step, max_down_step]. Then observe: the GPU rises; if it saturates, UP
    recovers it. This probe-and-observe resolves the "starved at low PL1 vs real
    headroom" ambiguity on its own and never sinks to min on a GPU-margin game.

Degradation:
  - GPU% available (AMD Ally/Legion, Steam Deck): the model above.
  - No GPU% (Intel Claw today: no gpu_busy): HOLD — can't optimise blind, no fake.
"""

# Responsive floor (watts) applied ONLY while the QAM / plugin UI is open. The loop
# is GPU-only, so a GPU-light game can sink PL1 to the device minimum (correct for
# the GPU) — but rendering the QAM is CPU-bound (steamwebhelper/CEF) and a starved
# PL1 makes the menu lag. Raising the loop's floor while the UI is open keeps
# interacting fluid; on close it drops back to device_min for battery. Device-aware
# (never below device_min). Tunable (on-device: 7 W lags, 15 W fluid → ~13 W).
RESPONSIVE_FLOOR_W = 13

_UP_GPU = 97       # a recent GPU% peak at/above this = saturated → step up (safety)
_DOWN_GPU = 88     # mean GPU% at/below this = headroom → the knee's lower edge
_RECENT = 2        # newest samples that define "recent" for the up trigger
_SLACK_HOLD = 6    # ticks of SUSTAINED headroom before a down move (~12 s @ 2 s)
# Watts of down-step per 1% the GPU sits below the knee. Makes the down move agile
# on a light scene (GPU far below the knee) and gentle near the knee, WITHOUT any
# watts reading — the step size comes from the GPU gap, then we observe the result.
_DOWN_GAIN = 1 / 3.0

# Boost detection: a sample "was boosting" when real draw exceeds PL1 by more than
# this many W. NOT used by the control loop any more (confounded on power-limited
# games); kept only for the telemetry boost metric / display, and for tdp/suggest
# to reason about *learned* history when it wants a draw-based hint.
BOOST_DEADBAND_W = 1


def _mean(xs):
    return sum(xs) / len(xs)


def effective_floor(device_min, ui_active, responsive_floor=RESPONSIVE_FLOOR_W):
    """The lower bound the loop passes to :func:`decide`.

    While the QAM / plugin UI is open (*ui_active*) raise it to *responsive_floor*
    so the CPU-bound menu render stays fluid; otherwise it is the device minimum.
    Device-aware: never below *device_min* (a device whose min already exceeds the
    responsive floor keeps its own min). Only the AUTO loop consults this.
    """
    if not ui_active:
        return device_min
    return max(device_min, responsive_floor)


def is_boosting(watts, pl1):
    """Was the chip boosting? ``draw > PL1 + deadband``. None when watts is
    unavailable. Retained for the telemetry boost metric / arc display — the
    control loop no longer consults it (draw is confounded on power-limited
    games)."""
    if watts is None:
        return None
    return round(watts) > round(pl1) + BOOST_DEADBAND_W


def decide(current_pl1, gpu_window, slack_ticks, min_w, max_w,
           *, up_step=2, down_step=1, max_down_step=5):
    """Next sustained PL1 and slack counter: ``(next_pl1, next_slack_ticks)``.

    *gpu_window* holds recent GPU% samples (newest-last), may contain None.
    *slack_ticks* is the running count of consecutive headroom ticks (the caller
    persists it between ticks). No GPU sample → hold (never guess).
    """
    cur = max(min_w, min(int(current_pl1), max_w))
    gpu = [x for x in gpu_window if x is not None]

    if not gpu:
        return cur, slack_ticks  # no signal → hold, preserve the counter

    # ---- UP (fast, wins) — a saturated GPU needs more power now --------------
    if max(gpu[-_RECENT:]) >= _UP_GPU:
        return max(min_w, min(cur + up_step, max_w)), 0

    avg = _mean(gpu)

    # ---- HOLD — mean GPU in the dead-band (the knee) -------------------------
    if avg > _DOWN_GPU:
        return cur, 0  # working near saturation, no headroom → hold, reset slack

    # ---- Sustained headroom: accumulate; at the gate, ONE proportional step --
    slack = slack_ticks + 1
    if slack < _SLACK_HOLD:
        return cur, slack  # not yet — hold, keep counting

    # Gate met. Step down, sized by how far the GPU is below the knee (agile on a
    # light scene, gentle near the knee), bounded. Never below min.
    gap = _DOWN_GPU - avg
    step = round(gap * _DOWN_GAIN)
    step = max(down_step, min(step, max_down_step))
    nxt = max(min_w, cur - step)
    return nxt, 0
