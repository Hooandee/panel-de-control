from tdp.reconcile import ReconcileMemory, after_apply, build_targets, decide
from tdp.types import RailReading, TdpObservation


def obs(value=15, lo=7, hi=30, surface="primary", rail="pl1"):
    return TdpObservation(
        readable=True,
        surfaces={surface: {rail: RailReading(value, lo, hi)}},
    )


def test_target_keeps_request_but_clamps_to_live_max():
    targets = build_targets(
        {"pl1": 25},
        {"pl1": {"min": 7, "max": 30}},
        obs(value=15, hi=15),
    )
    assert targets.requested == {"pl1": 25}
    assert targets.target == {"pl1": 15}
    assert targets.reasons == {"pl1": "live_max"}


def test_bogus_live_max_never_expands_safe_max():
    targets = build_targets(
        {"pl1": 150},
        {"pl1": {"min": 7, "max": 35}},
        obs(value=35, lo=5, hi=150),
    )
    assert targets.target == {"pl1": 35}
    assert targets.reasons == {"pl1": "safe_max"}


def test_each_rail_uses_its_own_live_floor():
    observation = TdpObservation(
        readable=True,
        surfaces={
            "primary": {
                "pl1": RailReading(10, 7, 30),
                "pl2": RailReading(15, 15, 43),
                "pl3": RailReading(15, 15, 53),
            },
        },
    )
    targets = build_targets(
        {"pl1": 10, "pl2": 10, "pl3": 10},
        {
            "pl1": {"min": 7, "max": 30},
            "pl2": {"min": 7, "max": 43},
            "pl3": {"min": 7, "max": 53},
        },
        observation,
    )
    assert targets.target == {"pl1": 10, "pl2": 15, "pl3": 15}
    assert targets.reasons == {"pl2": "live_min", "pl3": "live_min"}


def test_contradictory_live_bounds_prefer_the_lower_ceiling():
    targets = build_targets(
        {"pl1": 25},
        {"pl1": {"min": 7, "max": 35}},
        obs(value=15, lo=30, hi=15),
    )
    assert targets.target == {"pl1": 15}
    assert targets.reasons == {"pl1": "live_max"}


def test_matching_target_is_in_sync():
    targets = build_targets({"pl1": 15}, {"pl1": {"min": 7, "max": 30}}, obs())
    out = decide(targets, obs(), ReconcileMemory(), now=0.0, tolerance=0)
    assert (out.action, out.status) == ("hold", "in_sync")


def test_constrained_match_is_not_drift():
    limited = obs(value=15, hi=15)
    targets = build_targets(
        {"pl1": 25},
        {"pl1": {"min": 7, "max": 30}},
        limited,
    )
    out = decide(targets, limited, ReconcileMemory(), now=0.0, tolerance=0)
    assert (out.action, out.status, out.reason) == (
        "hold",
        "constrained",
        "live_max",
    )


def test_one_divergent_read_only_arms():
    targets = build_targets({"pl1": 15}, {"pl1": {"min": 7, "max": 30}}, obs())
    first = decide(targets, obs(value=30), ReconcileMemory(), now=10.0, tolerance=0)
    assert (first.action, first.status) == ("confirm_again", "settling")
    assert first.memory.pending_since == 10.0


def test_same_divergence_after_750ms_applies():
    targets = build_targets({"pl1": 15}, {"pl1": {"min": 7, "max": 30}}, obs())
    first = decide(targets, obs(value=30), ReconcileMemory(), now=10.0, tolerance=0)
    second = decide(targets, obs(value=30), first.memory, now=10.75, tolerance=0)
    assert (second.action, second.status, second.reason) == (
        "apply",
        "drift",
        "external_drift",
    )


def test_transient_clears_without_write():
    targets = build_targets({"pl1": 15}, {"pl1": {"min": 7, "max": 30}}, obs())
    first = decide(targets, obs(value=30), ReconcileMemory(), now=10.0, tolerance=0)
    second = decide(targets, obs(value=15), first.memory, now=10.75, tolerance=0)
    assert (second.action, second.status) == ("hold", "in_sync")
    assert second.memory.pending_signature is None


def test_apply_failure_uses_retry_ladder_then_degrades():
    targets = build_targets({"pl1": 15}, {"pl1": {"min": 7, "max": 30}}, obs())
    memory = ReconcileMemory()
    for expected_delay in (0.5, 2.0, 5.0):
        out = after_apply(
            targets,
            obs(value=30),
            memory,
            now=10.0,
            wrote_ok=False,
            tolerance=0,
        )
        assert out.status == "settling"
        assert out.memory.next_retry_at == 10.0 + expected_delay
        memory = out.memory
    out = after_apply(
        targets,
        obs(value=30),
        memory,
        now=10.0,
        wrote_ok=False,
        tolerance=0,
    )
    assert out.status == "rejected"
    assert out.memory.next_retry_at == 40.0


def test_write_only_heartbeat_is_unverifiable():
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        TdpObservation(readable=False),
    )
    out = decide(
        targets,
        TdpObservation(readable=False),
        ReconcileMemory(next_retry_at=15.0),
        now=15.0,
        tolerance=0,
        write_only=True,
    )
    assert (out.action, out.status, out.reason) == (
        "apply",
        "unverifiable",
        "read_unavailable",
    )


def test_write_only_apply_stays_unverifiable():
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        TdpObservation(readable=False),
    )
    out = after_apply(
        targets,
        TdpObservation(readable=False),
        ReconcileMemory(),
        now=10.0,
        wrote_ok=True,
        tolerance=0,
        write_only=True,
    )
    assert (out.status, out.reason) == ("unverifiable", "read_unavailable")
    assert out.memory.next_retry_at == 25.0


def test_readable_backend_retries_after_failed_empty_readback():
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        TdpObservation(readable=True),
    )
    failed = after_apply(
        targets,
        TdpObservation(readable=True),
        ReconcileMemory(),
        now=10.0,
        wrote_ok=False,
        tolerance=0,
    )
    due = decide(
        targets,
        TdpObservation(readable=True),
        failed.memory,
        now=10.5,
        tolerance=0,
    )
    assert (due.action, due.reason) == ("apply", "write_rejected")


def test_empty_readback_never_confirms_a_successful_write():
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        TdpObservation(readable=True),
    )
    out = after_apply(
        targets,
        TdpObservation(readable=True),
        ReconcileMemory(),
        now=10.0,
        wrote_ok=True,
        tolerance=0,
    )
    assert (out.status, out.reason) == ("unverifiable", "read_unavailable")


def test_any_asus_surface_can_report_drift():
    observation = TdpObservation(
        readable=True,
        surfaces={
            "armoury": {"pl1": RailReading(15, 7, 30)},
            "legacy": {"pl1": RailReading(30)},
        },
    )
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        observation,
    )
    first = decide(targets, observation, ReconcileMemory(), 0.0, 0)
    second = decide(targets, observation, first.memory, 0.75, 0)
    assert second.action == "apply"
    assert second.reason == "surface_mismatch"


def test_three_confirmed_drifts_in_30s_mark_persistent_conflict():
    memory = ReconcileMemory(drift_times=(1.0, 10.0))
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        obs(),
    )
    first = decide(targets, obs(value=30), memory, 20.0, 0)
    second = decide(targets, obs(value=30), first.memory, 20.75, 0)
    assert second.conflict_persistent is True


def test_persistent_conflict_survives_sync_until_window_expires():
    targets = build_targets(
        {"pl1": 15},
        {"pl1": {"min": 7, "max": 30}},
        obs(),
    )
    memory = ReconcileMemory(drift_times=(1.0, 10.0, 20.0))
    recent = decide(targets, obs(), memory, 21.0, 0)
    expired = decide(targets, obs(), recent.memory, 51.0, 0)
    assert recent.conflict_persistent is True
    assert expired.conflict_persistent is False
