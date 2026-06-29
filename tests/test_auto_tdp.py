from auto_tdp import decide, decide_fps


def test_ramps_up_at_full_load():
    assert decide(15, 100, min_w=5, max_w=30) == 17


def test_clamps_at_max_when_ramping_up():
    assert decide(29, 100, min_w=5, max_w=30) == 30


def test_already_at_max_stays_at_max():
    assert decide(30, 100, min_w=5, max_w=30) == 30


def test_ramps_down_at_low_load():
    assert decide(15, 50, min_w=5, max_w=30) == 13


def test_clamps_at_min_when_ramping_down():
    assert decide(6, 50, min_w=5, max_w=30) == 5


def test_already_at_min_stays_at_min():
    assert decide(5, 50, min_w=5, max_w=30) == 5


def test_holds_in_band_low_boundary():
    # 71 is the first value in the hold band (70 still ramps down)
    assert decide(15, 71, min_w=5, max_w=30) == 15


def test_ramps_down_at_exactly_70():
    assert decide(15, 70, min_w=5, max_w=30) == 13


def test_holds_in_band_high_boundary():
    # 94 is still in the hold band (>=95 ramps up)
    assert decide(15, 94, min_w=5, max_w=30) == 15


def test_ramps_up_at_exactly_95():
    assert decide(15, 95, min_w=5, max_w=30) == 17


def test_gpu_busy_none_holds():
    assert decide(15, None, min_w=5, max_w=30) == 15


def test_gpu_busy_none_clamps_to_range():
    # current value outside bounds with no signal → clamp, not guess
    assert decide(50, None, min_w=5, max_w=30) == 30
    assert decide(0, None, min_w=5, max_w=30) == 5


def test_custom_step():
    assert decide(15, 100, min_w=5, max_w=30, step=5) == 20


def test_current_above_max_clamped_before_ramp():
    # If current PL1 drifted above max_w, clamp first then apply step
    assert decide(40, 100, min_w=5, max_w=30) == 30  # clamped to 30 first, then +step but still 30


# ---------------------------------------------------------------------------
# decide_fps — FPS-target controller
# ---------------------------------------------------------------------------

def test_fps_below_target_ramps_up():
    # fps=40, target=60, margin=3 → fps < 57 → ramp up
    assert decide_fps(15, fps=40, target_fps=60, min_w=5, max_w=30) == 17


def test_fps_below_target_clamps_at_max():
    assert decide_fps(29, fps=30, target_fps=60, min_w=5, max_w=30) == 30


def test_fps_above_target_ramps_down():
    # fps=70, target=60, margin=3 → fps > 63 → ramp down
    assert decide_fps(15, fps=70, target_fps=60, min_w=5, max_w=30) == 13


def test_fps_above_target_clamps_at_min():
    assert decide_fps(6, fps=90, target_fps=60, min_w=5, max_w=30) == 5


def test_fps_within_margin_holds():
    # within ±3 of 60 (57..63) → hold
    assert decide_fps(15, fps=60, target_fps=60, min_w=5, max_w=30) == 15
    assert decide_fps(15, fps=57, target_fps=60, min_w=5, max_w=30) == 15
    assert decide_fps(15, fps=63, target_fps=60, min_w=5, max_w=30) == 15


def test_fps_just_outside_margin_ramps():
    # 56 is just below 57 → ramp up
    assert decide_fps(15, fps=56, target_fps=60, min_w=5, max_w=30) == 17
    # 64 is just above 63 → ramp down
    assert decide_fps(15, fps=64, target_fps=60, min_w=5, max_w=30) == 13


def test_fps_none_holds():
    assert decide_fps(15, fps=None, target_fps=60, min_w=5, max_w=30) == 15


def test_target_none_holds():
    assert decide_fps(15, fps=60, target_fps=None, min_w=5, max_w=30) == 15


def test_fps_and_target_none_holds():
    assert decide_fps(15, fps=None, target_fps=None, min_w=5, max_w=30) == 15


def test_fps_none_clamps_to_range():
    assert decide_fps(50, fps=None, target_fps=60, min_w=5, max_w=30) == 30
    assert decide_fps(0, fps=None, target_fps=None, min_w=5, max_w=30) == 5


def test_fps_custom_step():
    assert decide_fps(15, fps=30, target_fps=60, min_w=5, max_w=30, step=5) == 20
