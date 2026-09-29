from tdp.overshoot import (
    ESCALATE_HOLD_S,
    NUDGE,
    REASSERT_S,
    REWRITE,
    SUSTAIN_S,
    VERIFY_S,
    HiddenOvershootMonitor,
    nudged_target,
    overshoot_limit,
    sustained_ceiling,
)

FLAT_20 = {"pl1": 20, "pl2": 20, "pl3": 20}
GAME = "game-a"

# Ally X RC72LA on AC: rails read 20/20/20 in sync while the chip drew these
# watts (5 s telemetry). A 19 -> 20 write brought it back to 20.0 W.
ALLY_X_AC_OVERSHOOT = [21.5, 38.1, 40.2, 42.9, 44.0, 42.6, 43.0, 43.5, 43.2, 43.0]


def feed(monitor, samples, start=0.0, step=2.0, target=FLAT_20, eligible=True):
    actions = []
    now = start
    for watts in samples:
        action = monitor.observe(now, GAME, watts, target, eligible)
        if action is not None:
            actions.append((now, action))
        now += step
    return actions, now


def test_ceiling_uses_the_sustained_rails_not_the_fast_one():
    assert sustained_ceiling({"pl1": 15, "pl2": 15, "pl3": 30}) == 15
    assert sustained_ceiling({"pl1": 15, "pl2": 17, "pl3": 20}) == 17
    assert sustained_ceiling({"pl1": 11}) == 11
    assert overshoot_limit(20) == 26.0
    assert overshoot_limit(40) == 50.0


def test_normal_draw_at_or_near_the_limit_never_triggers():
    monitor = HiddenOvershootMonitor()
    actions, _ = feed(monitor, [20.0, 21.5, 25.9, 24.0] * 30)
    assert actions == []
    assert monitor.last is None


def test_short_burst_above_the_limit_never_triggers():
    monitor = HiddenOvershootMonitor()
    burst = [40.0] * int(SUSTAIN_S / 2) + [20.0]
    actions, _ = feed(monitor, burst * 5)
    assert actions == []


def test_ally_x_sustained_overshoot_rewrites_then_verifies_restoration():
    monitor = HiddenOvershootMonitor()
    actions, now = feed(monitor, ALLY_X_AC_OVERSHOOT + [43.0] * 2)
    assert [action for _, action in actions] == [REWRITE]
    feed(monitor, [20.0], start=now)
    last = monitor.last
    assert last["state"] == "restored"
    assert last["method"] == REWRITE
    assert last["peak_w"] >= 44.0
    assert last["settled_w"] == 20.0


def test_rewrite_that_does_not_help_escalates_to_nudge_then_gives_up():
    monitor = HiddenOvershootMonitor()
    samples = [43.0] * int((SUSTAIN_S + 2 * VERIFY_S) / 2 + 4)
    actions, _ = feed(monitor, samples)
    assert [action for _, action in actions] == [REWRITE, NUDGE]
    assert monitor.last["state"] == "unresolved"


def test_nudge_that_worked_becomes_the_first_correction_next_time():
    monitor = HiddenOvershootMonitor()
    first = [43.0] * int((SUSTAIN_S + VERIFY_S) / 2 + 2) + [20.0]
    actions, now = feed(monitor, first)
    assert [action for _, action in actions] == [REWRITE, NUDGE]
    assert monitor.last["state"] == "restored"
    assert monitor.preferred_method == NUDGE
    actions, _ = feed(monitor, [43.0] * 12, start=now)
    assert [action for _, action in actions] == [NUDGE]


def test_unresolved_backs_off_and_stops_after_three_attempts():
    monitor = HiddenOvershootMonitor()
    actions, _ = feed(monitor, [43.0] * 2000)
    methods = [action for _, action in actions]
    assert methods == [REWRITE, NUDGE] * 3
    starts = [at for at, action in actions if action == REWRITE]
    assert starts[1] - starts[0] >= 60.0
    assert starts[2] - starts[1] >= 180.0


def test_ineligible_or_unknown_power_never_acts():
    monitor = HiddenOvershootMonitor()
    assert feed(monitor, [43.0] * 40, eligible=False)[0] == []
    assert feed(monitor, [None] * 40)[0] == []


def test_low_setpoints_below_the_firmware_floor_are_ignored():
    monitor = HiddenOvershootMonitor()
    floor = {"pl1": 5, "pl2": 5, "pl3": 5}
    assert feed(monitor, [19.0] * 60, target=floor)[0] == []


def test_target_change_mid_correction_drops_the_episode():
    monitor = HiddenOvershootMonitor()
    actions, now = feed(monitor, [43.0] * 11)
    assert [action for _, action in actions] == [REWRITE]
    other = {"pl1": 25, "pl2": 25, "pl3": 25}
    assert monitor.observe(now, GAME, 43.0, other, True) is None
    assert monitor.as_dict(now)["correcting"] is False


def test_repeated_restorations_enable_a_bounded_periodic_reassert():
    monitor = HiddenOvershootMonitor()
    now = 0.0
    for _ in range(2):
        _, now = feed(monitor, [43.0] * 11 + [20.0], start=now)
        now += 60.0
    assert monitor.reassert_s(now, GAME) == REASSERT_S
    assert monitor.reassert_s(now, "other-game") is None
    assert monitor.reassert_s(now + ESCALATE_HOLD_S + 1, GAME) is None


def test_a_single_restoration_does_not_enable_periodic_writes():
    monitor = HiddenOvershootMonitor()
    _, now = feed(monitor, [43.0] * 11 + [20.0])
    assert monitor.reassert_s(now, GAME) is None


def test_game_change_resets_the_session():
    monitor = HiddenOvershootMonitor()
    for _ in range(2):
        feed(monitor, [43.0] * 11 + [20.0])
    monitor.observe(10_000.0, "game-b", 20.0, FLAT_20, True)
    assert monitor.reassert_s(10_000.0, GAME) is None
    assert monitor.last is None


def test_nudge_moves_each_rail_inside_its_bounds():
    bounds = {"pl1": (7, 30), "pl2": (15, 43), "pl3": (15, 53)}
    assert nudged_target(FLAT_20, bounds) == {"pl1": 19, "pl2": 19, "pl3": 19}
    floor = {"pl1": 7, "pl2": 15, "pl3": 15}
    assert nudged_target(floor, bounds) == {"pl1": 8, "pl2": 16, "pl3": 16}
    assert nudged_target({"pl1": 7}, {"pl1": (7, 7)}) is None


def test_interrupted_correction_clears_the_correcting_notice():
    monitor = HiddenOvershootMonitor()
    feed(monitor, [43.0] * 11)
    assert monitor.last["state"] == "correcting"
    monitor.observe(100.0, GAME, 43.0, FLAT_20, False)
    assert monitor.last is None


def test_steam_deck_slow_fast_rail_model_is_left_alone():
    monitor = HiddenOvershootMonitor()
    deck_target = {"pl2": 15, "pl3": 15}
    assert sustained_ceiling(deck_target) is None
    assert feed(monitor, [40.0] * 60, target=deck_target)[0] == []
