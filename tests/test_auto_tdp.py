from auto_tdp import decide, effective_floor

# decide — GPU-UTILISATION driven control with a dead-band + temporal hysteresis
# + proportional (observed) down-step. Watts/boost are NOT used: on a power-limited
# game the draw follows PL1, so ANY draw-derived signal (boost magnitude, boost
# frequency, watts headroom) is confounded — it can't tell "has margin" from "needs
# it". GPU utilisation is the only honest "can it go lower?" signal (80% busy at the
# cap = not saturated = there IS margin).
#
#   Signature: decide(cur, gpu_window, slack_ticks, min_w, max_w,
#                      *, up_step=2, down_step=1, max_down_step=5)
#   Returns:   (next_pl1, next_slack_ticks)
#
#   UP:   recent GPU peak >= _UP_GPU (97) → +up_step (saturated → needs more).
#   DOWN: mean GPU SUSTAINED <= _DOWN_GPU (88) for _SLACK_HOLD ticks → step down,
#         proportional to how far GPU is below the knee (agile for light scenes,
#         gentle near the knee), bounded [down_step, max_down_step].
#   HOLD: mean GPU in the dead-band (88..97) = the knee → stable (kills sawtooth).
#   Level 4 (no GPU sample): HOLD.
# Probe-and-observe: after a down step the GPU rises; if it saturates, UP recovers
# → never sinks to min on a game with GPU margin, converges on the knee (~90-95%).

_SLACK_HOLD = 6   # ticks of sustained GPU headroom before a down move (~12 s @ 2 s)


def g(*s):
    return list(s)


# ===========================================================================
# UP — recent GPU saturation (protect FPS)
# ===========================================================================

def test_gpu_peak_steps_up():
    nxt, slack = decide(20, g(95, 96, 97, 96, 97), 0, 5, 35)
    assert nxt == 22 and slack == 0  # +up_step(2), slack reset


def test_recent_peak_ignores_single_dip():
    # last 2 = [97, 80] → peak 97 → still saturated → up
    nxt, _ = decide(20, g(90, 90, 90, 97, 80), 0, 5, 35)
    assert nxt == 22


def test_up_clamps_at_max():
    nxt, _ = decide(34, g(99, 99, 99), 0, 5, 35)
    assert nxt == 35


# ===========================================================================
# HOLD — dead-band (knee) + power-limited-at-max case
# ===========================================================================

def test_deadband_holds():
    # GPU ~92% (in 88..97 dead-band) = the knee → hold, no sawtooth
    nxt, slack = decide(25, g(91, 92, 93, 92, 91), 3, 5, 35)
    assert nxt == 25 and slack == 0  # not headroom → reset, hold


def test_power_limited_at_max_still_probes_down():
    # The power-limited case: pl1=35 (max), GPU stable 80% (below _DOWN_GPU) → there IS
    # margin (not saturated) even though draw pinned the cap. Must accumulate slack
    # and eventually step down — NOT hold forever at max.
    nxt, slack = decide(35, g(80, 81, 80, 81, 80), _SLACK_HOLD - 1, 5, 35)
    assert nxt < 35 and slack == 0  # stepped down off the cap


# ===========================================================================
# DOWN — sustained GPU headroom gate (temporal hysteresis) + proportional step
# ===========================================================================

def test_headroom_below_gate_accumulates():
    nxt, slack = decide(25, g(80, 80, 80), 2, 5, 35)
    assert nxt == 25 and slack == 3  # accumulate, hold


def test_headroom_reaches_gate_steps_down():
    nxt, slack = decide(25, g(84, 85, 84), _SLACK_HOLD - 1, 5, 35)
    assert nxt < 25 and slack == 0  # gentle step (GPU near knee)


def test_proportional_step_gentle_near_knee():
    # GPU 85 (gap 3 below knee) → round(3/3)=1 → -1 (gentle near the knee)
    nxt, _ = decide(25, g(85, 85, 85), _SLACK_HOLD - 1, 5, 35)
    assert nxt == 24


def test_proportional_step_aggressive_when_light():
    # GPU 55 (gap 33, light scene) → round(11) → bounded to max_down_step(5)
    nxt, _ = decide(25, g(55, 55, 55), _SLACK_HOLD - 1, 5, 35)
    assert nxt == 20  # agile down on a light scene


def test_down_step_bounded_by_max():
    # GPU 5 (extreme) → still capped at max_down_step, never a wild jump
    nxt, _ = decide(30, g(5, 5, 5), _SLACK_HOLD - 1, 5, 35)
    assert nxt == 25  # -5, bounded


def test_down_floors_at_min():
    nxt, _ = decide(7, g(30, 30, 30), _SLACK_HOLD - 1, 5, 35)
    assert nxt == 5  # -5 would be 2, floored to min


def test_transient_headroom_dip_does_not_drop():
    # one headroom tick then dead-band activity → slack resets, never reaches gate
    nxt1, s1 = decide(25, g(80, 80, 80), 0, 5, 35)
    assert nxt1 == 25 and s1 == 1
    nxt2, s2 = decide(25, g(92, 92, 92), s1, 5, 35)
    assert nxt2 == 25 and s2 == 0  # dead-band resets


# ===========================================================================
# Level 4 — no GPU signal (Claw today): HOLD, never thrash
# ===========================================================================

def test_no_gpu_holds():
    nxt, slack = decide(18, g(), 4, 5, 35)
    assert nxt == 18 and slack == 4  # no signal → hold, preserve slack


def test_all_none_holds():
    nxt, _ = decide(18, g(None, None), 0, 5, 35)
    assert nxt == 18


def test_clamps_current_into_range():
    nxt, _ = decide(50, g(), 0, 5, 35)
    assert nxt == 35
    nxt, _ = decide(0, g(), 0, 5, 35)
    assert nxt == 5


# ===========================================================================
# None-safety in the window
# ===========================================================================

def test_none_samples_ignored_in_peak():
    nxt, _ = decide(20, g(None, 80, None, 97, 96), 0, 5, 35)
    assert nxt == 22  # real last-2 = [97, 96] → up


def test_none_samples_ignored_in_mean():
    # real samples are all headroom (80) → at the gate → step down
    nxt, _ = decide(25, g(None, 80, None, 80), _SLACK_HOLD - 1, 5, 35)
    assert nxt < 25


# ===========================================================================
# Tunable steps
# ===========================================================================

def test_custom_up_step():
    nxt, _ = decide(20, g(99, 99), 0, 5, 35, up_step=5)
    assert nxt == 25


def test_custom_max_down_step():
    nxt, _ = decide(30, g(50, 50, 50), _SLACK_HOLD - 1, 5, 35, max_down_step=3)
    assert nxt == 27  # bounded to 3 instead of 5


# ===========================================================================
# effective_floor — QAM-open responsive floor (CPU-bound blind-spot fix)
# ===========================================================================
# The auto loop is GPU-only, so a GPU-light game can sink PL1 to device_min (7 W)
# — correct for the GPU, but rendering the QAM is CPU-bound (steamwebhelper/CEF)
# and PL1=7 starves it → the QAM lags. While the QAM/UI is OPEN we raise the floor
# the loop passes to decide to a responsive floor so interacting stays fluid; on
# close it drops back to device_min so the loop can go low again for battery.

def test_floor_is_device_min_when_ui_closed():
    assert effective_floor(7, False, 13) == 7


def test_floor_rises_to_responsive_when_ui_open():
    assert effective_floor(7, True, 13) == 13


def test_floor_never_below_device_min_when_ui_open():
    # A device whose min already exceeds the responsive floor keeps its own min.
    assert effective_floor(15, True, 13) == 15


def test_responsive_floor_below_device_min_is_ignored():
    assert effective_floor(10, True, 8) == 10
