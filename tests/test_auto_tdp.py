import pytest

from auto_tdp import AutoTdpController


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def controller(initial=15, minimum=5, maximum=35, target=40, **timing):
    clock = timing.pop("clock", Clock())
    control = AutoTdpController(
        initial_w=initial,
        min_w=minimum,
        max_w=maximum,
        target_fps=target,
        clock=clock,
        warmup_s=timing.get("warmup_s", 10),
        stable_s=timing.get("stable_s", 20),
        settle_s=timing.get("settle_s", 8),
        cooldown_s=timing.get("cooldown_s", 30),
        qualification_s=timing.get("qualification_s", 0),
        low_load_qualification_s=timing.get("low_load_qualification_s", 60),
    )
    control.test_clock = clock
    return control


def step(control, fps=40.0, reason="ok", gpu=70.0, after=0):
    control.test_clock.advance(after)
    return control.step(
        fps=fps,
        signal_reason=reason,
        gpu_busy=gpu,
    )


def reach_probe(control, interval=10):
    step(control, fps=40.0)
    return step(control, fps=40.1, after=interval)


def test_warmup_holds_user_initial_tdp_for_elapsed_time():
    control = controller(initial=18, warmup_s=10)

    first = step(control)
    second = step(control, after=9)
    ready = step(control, after=1)

    assert (first.setpoint, first.state, first.changed) == (18, "warming", False)
    assert (second.setpoint, second.state, second.changed) == (18, "warming", False)
    assert ready.state == "holding"


def test_default_cadence_probes_at_twenty_seconds_then_protects_each_drop():
    clock = Clock()
    control = AutoTdpController(
        initial_w=15,
        min_w=3,
        max_w=15,
        target_fps=60,
        clock=clock,
    )

    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(8)
    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(4)
    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(7)
    before_first_probe = control.step(
        fps=90,
        signal_reason="ok",
        gpu_busy=60,
    )
    clock.advance(1)
    first_probe = control.step(fps=90, signal_reason="ok", gpu_busy=60)

    assert before_first_probe.setpoint == 15
    assert (first_probe.setpoint, first_probe.reason) == (14, "probe_down")

    control.confirm_apply()
    clock.advance(2)
    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(4)
    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(12)
    control.step(fps=90, signal_reason="ok", gpu_busy=60)
    clock.advance(7)
    before_second_probe = control.step(
        fps=90,
        signal_reason="ok",
        gpu_busy=60,
    )
    clock.advance(8)
    second_probe = control.step(fps=90, signal_reason="ok", gpu_busy=60)

    assert before_second_probe.setpoint == 14
    assert (second_probe.setpoint, second_probe.reason) == (13, "probe_down")


def test_default_low_demand_cadence_reaches_first_probe_in_twenty_four_seconds():
    clock = Clock()
    control = AutoTdpController(
        initial_w=15,
        min_w=3,
        max_w=15,
        target_fps=60,
        clock=clock,
    )

    control.step(fps=60, signal_reason="ok", gpu_busy=8)
    clock.advance(12)
    control.step(fps=60, signal_reason="ok", gpu_busy=8)
    clock.advance(4)
    control.step(fps=60, signal_reason="ok", gpu_busy=8)
    clock.advance(7)
    before_probe = control.step(fps=60, signal_reason="ok", gpu_busy=8)
    clock.advance(1)
    probe = control.step(fps=60, signal_reason="ok", gpu_busy=8)

    assert before_probe.setpoint == 15
    assert (probe.setpoint, probe.reason) == (14, "probe_down")


@pytest.mark.parametrize(
    "reason",
    ["fps_unavailable", "fps_stale", "focus_mismatch", "no_game_focus"],
)
def test_unreliable_fps_pauses_without_changing_tdp(reason):
    control = controller(initial=17)

    result = step(control, fps=None, reason=reason)

    assert (result.setpoint, result.state, result.changed) == (17, "paused", False)
    assert result.reason == reason


def test_fps_deficit_recovers_two_watts_without_waiting_for_warmup():
    control = controller(initial=15, maximum=30)

    result = step(control, fps=36.5)

    assert (result.setpoint, result.state, result.changed) == (17, "recovering", True)
    assert result.reason == "fps_below_target"


def test_recent_low_fps_keeps_recovering_through_a_short_stale_gap():
    control = controller(initial=5, maximum=30)

    fresh = step(control, fps=36, gpu=99)
    first_stale = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=6,
    )
    second_stale = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=2,
    )
    third_stale = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=2,
    )

    assert [
        (decision.setpoint, decision.state, decision.reason)
        for decision in (fresh, first_stale, second_stale, third_stale)
    ] == [
        (7, "recovering", "fps_below_target"),
        (9, "recovering", "fps_stale_recovery"),
        (11, "recovering", "fps_stale_recovery"),
        (13, "recovering", "fps_stale_recovery"),
    ]


def test_stale_recovery_expires_and_never_uses_low_gpu_load():
    expired = controller(initial=5, maximum=30)
    low_load = controller(initial=5, maximum=30)

    step(expired, fps=36, gpu=99)
    expired_result = step(
        expired,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=11.1,
    )
    step(low_load, fps=36, gpu=99)
    low_load_result = step(
        low_load,
        fps=None,
        reason="fps_stale",
        gpu=89,
        after=2,
    )

    assert (expired_result.setpoint, expired_result.state) == (7, "paused")
    assert expired_result.reason == "fps_stale"
    assert (low_load_result.setpoint, low_load_result.state) == (7, "paused")
    assert low_load_result.reason == "fps_stale"


def test_stale_recovery_waits_for_its_two_second_step_interval():
    control = controller(initial=5, maximum=30)

    step(control, fps=36, gpu=99)
    waiting = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=1,
    )
    recovered = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=1,
    )

    assert (waiting.setpoint, waiting.state, waiting.changed) == (
        7,
        "recovering",
        False,
    )
    assert waiting.reason == "fps_stale_recovery_wait"
    assert (recovered.setpoint, recovered.reason) == (9, "fps_stale_recovery")


def test_stale_recovery_needs_a_confirmed_low_fps_sample():
    control = controller(initial=15, maximum=30)

    result = step(
        control,
        fps=None,
        reason="fps_stale",
        gpu=99,
        after=2,
    )

    assert (result.setpoint, result.state, result.changed) == (
        15,
        "paused",
        False,
    )
    assert result.reason == "fps_stale"


def test_stable_fps_only_probes_down_one_watt_after_full_duration():
    control = controller(initial=20, warmup_s=0, stable_s=20)

    assert step(control, fps=40.2).setpoint == 20
    assert step(control, fps=40.1, after=19).setpoint == 20
    result = step(control, fps=40.0, after=1)

    assert (result.setpoint, result.state, result.changed) == (19, "optimizing", True)
    assert result.reason == "probe_down"


def test_probe_cadence_depends_on_elapsed_time_not_sample_count():
    fast = controller(initial=20, warmup_s=0, stable_s=20)
    slow = controller(initial=20, warmup_s=0, stable_s=20)

    for _ in range(21):
        fast_result = step(fast, after=1)
    for _ in range(3):
        slow_result = step(slow, after=10)

    assert fast_result.reason == "probe_down"
    assert slow_result.reason == "probe_down"
    assert fast_result.setpoint == slow_result.setpoint == 19


def test_sixty_hz_menu_holds_initial_until_gameplay_is_qualified():
    control = controller(
        initial=20,
        target=60,
        warmup_s=0,
        stable_s=2,
        qualification_s=10,
    )

    for _ in range(8):
        result = step(control, fps=60, gpu=8, after=5)

    assert (result.setpoint, result.state, result.changed) == (20, "holding", False)
    assert result.reason == "awaiting_gameplay"


def test_low_demand_game_qualifies_slowly_then_probes_one_watt():
    control = controller(
        initial=15,
        target=60,
        warmup_s=0,
        stable_s=2,
        qualification_s=10,
        low_load_qualification_s=60,
    )

    assert step(control, fps=60, gpu=8).reason == "awaiting_gameplay"
    assert step(control, fps=60, gpu=9, after=59).reason == "awaiting_gameplay"
    qualified = step(control, fps=60, gpu=8, after=1)
    probe = step(control, fps=60, gpu=9, after=2)

    assert qualified.reason == "building_stability"
    assert (probe.setpoint, probe.reason, probe.changed) == (14, "probe_down", True)


def test_low_load_qualification_restarts_after_an_fps_deficit():
    control = controller(
        initial=15,
        target=60,
        warmup_s=0,
        low_load_qualification_s=60,
    )
    step(control, fps=60, gpu=8)
    step(control, fps=60, gpu=9, after=59)
    step(control, fps=40, gpu=9, after=1)
    control.confirm_apply()

    resumed = step(control, fps=60, gpu=8, after=1)

    assert resumed.reason == "awaiting_gameplay"


def test_fps_far_above_target_probes_down_after_stable_demand():
    control = controller(
        initial=20,
        target=40,
        warmup_s=0,
        stable_s=2,
        qualification_s=0,
    )

    step(control, fps=60, gpu=80)
    result = step(control, fps=65, gpu=80, after=2)

    assert (result.setpoint, result.state, result.changed) == (19, "optimizing", True)
    assert result.reason == "probe_down"


def test_relative_load_collapse_freezes_an_active_probe():
    control = controller(
        initial=20,
        target=60,
        warmup_s=0,
        stable_s=2,
        settle_s=2,
        qualification_s=0,
    )

    assert step(control, fps=60, gpu=75).setpoint == 20
    probe = step(control, fps=60, gpu=72, after=2)
    assert probe.setpoint == 19
    control.confirm_apply()

    menu = step(control, fps=60, gpu=8, after=1)

    assert (menu.setpoint, menu.state, menu.changed) == (19, "paused", False)
    assert menu.reason == "load_shift"


def test_low_fps_recovers_even_when_secondary_signals_look_like_low_demand():
    control = controller(initial=20, warmup_s=0)

    result = step(control, fps=12, gpu=8)

    assert (result.setpoint, result.state, result.changed) == (22, "recovering", True)
    assert result.reason == "fps_below_target"


def test_qualified_load_collapse_recovers_for_a_low_fps_sample():
    control = controller(initial=20, target=60, warmup_s=0, qualification_s=0)
    step(control, fps=60, gpu=75)

    menu = step(control, fps=20, gpu=8, after=1)

    assert (menu.setpoint, menu.state, menu.changed) == (22, "recovering", True)
    assert menu.reason == "fps_below_target"


def test_low_load_session_restores_its_starting_tdp_when_demand_returns():
    control = controller(
        initial=15,
        target=60,
        warmup_s=0,
        stable_s=0,
        low_load_qualification_s=0,
    )
    step(control, fps=60, gpu=8)
    probe = step(control, fps=60, gpu=9)
    assert probe.setpoint == 14
    control.confirm_apply()

    gameplay = step(control, fps=25, gpu=55, after=1)

    assert (gameplay.setpoint, gameplay.state, gameplay.changed) == (
        15,
        "recovering",
        True,
    )
    assert gameplay.reason == "load_increase"


def test_failed_probe_rolls_back_immediately_to_last_stable_tdp():
    control = controller(initial=15, warmup_s=0, stable_s=10)
    probe = reach_probe(control)
    assert probe.setpoint == 14
    control.confirm_apply()

    rollback = step(control, fps=36.0, after=5)

    assert (rollback.setpoint, rollback.state, rollback.changed) == (
        15,
        "recovering",
        True,
    )
    assert rollback.reason == "probe_regressed"


def test_probe_rolls_back_on_small_regression_before_large_deficit():
    control = controller(initial=15, warmup_s=0, stable_s=10)
    reach_probe(control)
    control.confirm_apply()

    rollback = step(control, fps=38.2, after=5)

    assert rollback.setpoint == 15
    assert rollback.reason == "probe_regressed"


@pytest.mark.parametrize(
    "reason",
    ["fps_stale", "focus_mismatch", "no_game_focus"],
)
def test_signal_loss_during_probe_restores_last_stable_tdp(reason):
    control = controller(initial=15, warmup_s=0, stable_s=10)
    probe = reach_probe(control)
    assert probe.setpoint == 14
    control.confirm_apply()

    paused = step(control, fps=None, reason=reason, after=1)

    assert (paused.setpoint, paused.state, paused.changed) == (15, "paused", True)
    assert paused.reason == reason


def test_rejected_probe_apply_restores_previous_setpoint_and_pauses():
    control = controller(initial=15, warmup_s=0, stable_s=10)
    reach_probe(control)

    rejected = control.reject_apply("apply_unconfirmed")

    assert (rejected.setpoint, rejected.state, rejected.changed) == (
        15,
        "paused",
        True,
    )
    assert rejected.reason == "apply_unconfirmed"


def test_successful_probe_stays_protected_through_cooldown():
    control = controller(
        initial=15,
        warmup_s=0,
        stable_s=10,
        settle_s=8,
        cooldown_s=30,
    )
    probe = reach_probe(control)
    assert probe.setpoint == 14
    control.confirm_apply()

    settling = step(control, fps=40.0, after=4)
    guarded = step(control, fps=40.1, after=4)
    cooldown = step(control, fps=40.0, after=29)
    accepted = step(control, fps=40.0, after=1)

    assert (settling.state, settling.setpoint) == ("optimizing", 14)
    assert (guarded.state, guarded.reason, guarded.setpoint) == (
        "holding",
        "cooldown",
        14,
    )
    assert (cooldown.state, cooldown.reason, cooldown.setpoint) == (
        "holding",
        "cooldown",
        14,
    )
    assert (accepted.state, accepted.reason, accepted.setpoint) == (
        "holding",
        "probe_stable",
        14,
    )


def test_probe_remains_reversible_until_cooldown_finishes():
    control = controller(
        initial=6,
        minimum=3,
        maximum=15,
        target=60,
        warmup_s=0,
        stable_s=1,
        settle_s=6,
        cooldown_s=12,
        qualification_s=0,
    )
    step(control, fps=60, gpu=70)
    probe = step(control, fps=60, gpu=70, after=1)
    assert (probe.setpoint, probe.reason) == (5, "probe_down")
    control.confirm_apply()

    step(control, fps=60, gpu=70, after=5)
    guarded = step(control, fps=60, gpu=70, after=1)
    regression = step(control, fps=59, gpu=70, after=1)

    assert (guarded.setpoint, guarded.reason) == (5, "cooldown")
    assert (regression.setpoint, regression.reason) == (6, "probe_regressed")


def test_failed_safe_rollback_keeps_safe_setpoint_for_retry():
    control = controller(
        initial=6,
        minimum=3,
        maximum=15,
        target=60,
        warmup_s=0,
        stable_s=1,
        qualification_s=0,
    )
    step(control, fps=60, gpu=70)
    step(control, fps=60, gpu=70, after=1)
    control.confirm_apply()
    rollback = step(control, fps=59, gpu=70, after=1)

    rejected = control.reject_apply("apply_failed")

    assert (rollback.setpoint, rollback.reason) == (6, "probe_regressed")
    assert (rejected.setpoint, rejected.state, rejected.changed) == (
        6,
        "paused",
        False,
    )
    assert rejected.reason == "apply_failed"


def test_general_recovery_resumes_after_probe_cooldown_finishes():
    control = controller(
        initial=6,
        minimum=3,
        maximum=15,
        target=60,
        warmup_s=0,
        stable_s=1,
        settle_s=6,
        cooldown_s=12,
        qualification_s=0,
    )
    step(control, fps=60, gpu=70)
    step(control, fps=60, gpu=70, after=1)
    control.confirm_apply()
    step(control, fps=60, gpu=70, after=5)
    step(control, fps=60, gpu=70, after=1)

    accepted = step(control, fps=60, gpu=70, after=12)
    deficit = step(control, fps=55, gpu=70, after=2)

    assert accepted.reason == "probe_stable"
    assert (deficit.setpoint, deficit.reason) == (7, "fps_below_target")


def test_failed_probe_waits_two_minutes_before_trying_lower_again():
    control = controller(
        initial=6,
        minimum=3,
        maximum=15,
        target=60,
        warmup_s=0,
        stable_s=1,
        settle_s=0,
        cooldown_s=0,
        qualification_s=0,
    )
    step(control, fps=60, gpu=70)
    step(control, fps=60, gpu=70, after=1)
    control.confirm_apply()
    rollback = step(control, fps=59, gpu=70, after=1)
    control.confirm_apply()

    step(control, fps=60, gpu=70, after=60)
    held = step(control, fps=60, gpu=70, after=1)
    step(control, fps=60, gpu=70, after=59)
    retry = step(control, fps=60, gpu=70, after=1)

    assert (rollback.setpoint, rollback.reason) == (6, "probe_regressed")
    assert (held.setpoint, held.reason) == (6, "cooldown")
    assert (retry.setpoint, retry.reason) == (5, "probe_down")


def test_failed_probe_backoff_never_delays_recovery():
    control = controller(
        initial=6,
        minimum=3,
        maximum=15,
        target=60,
        warmup_s=0,
        stable_s=1,
        settle_s=0,
        cooldown_s=0,
        qualification_s=0,
    )
    step(control, fps=60, gpu=70)
    step(control, fps=60, gpu=70, after=1)
    control.confirm_apply()
    step(control, fps=59, gpu=70, after=1)
    control.confirm_apply()

    recovery = step(control, fps=55, gpu=100, after=2)

    assert (recovery.setpoint, recovery.reason) == (8, "fps_below_target")


def test_recovery_and_probe_are_clamped_to_device_limits():
    upper = controller(initial=34, maximum=35, warmup_s=0)
    lower = controller(initial=5, minimum=5, warmup_s=0, stable_s=0)

    assert step(upper, fps=20).setpoint == 35
    upper.confirm_apply()
    at_max = step(upper, fps=20)
    assert (at_max.setpoint, at_max.changed, at_max.reason) == (
        35,
        False,
        "at_maximum",
    )
    step(lower, fps=40)
    at_min = step(lower, fps=40)
    assert (at_min.setpoint, at_min.changed, at_min.reason) == (
        5,
        False,
        "at_minimum",
    )


def test_resume_after_pause_restarts_warmup_before_optimizing():
    control = controller(initial=16, warmup_s=10, stable_s=0)
    step(control, fps=None, reason="fps_stale")

    first = step(control, fps=40)
    second = step(control, fps=40, after=9)

    assert first.state == "warming" and first.setpoint == 16
    assert second.state == "warming" and second.setpoint == 16
