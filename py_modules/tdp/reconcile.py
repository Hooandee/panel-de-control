from dataclasses import dataclass, field, replace

CONFIRM_S = 0.75
VERIFY_S = 0.5
MIN_CORRECTION_S = 2.0
RETRY_S = (0.5, 2.0, 5.0)
DEGRADED_RETRY_S = 30.0
CONFLICT_WINDOW_S = 30.0
CONFLICT_COUNT = 3
UNVERIFIABLE_HEARTBEAT_S = 15.0


@dataclass(frozen=True)
class TargetSet:
    requested: dict[str, int]
    target: dict[str, int]
    reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconcileMemory:
    pending_signature: tuple | None = None
    pending_since: float | None = None
    failures: int = 0
    next_retry_at: float = 0.0
    last_write_at: float | None = None
    drift_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class ReconcileDecision:
    action: str
    status: str
    reason: str
    memory: ReconcileMemory
    conflict_persistent: bool = False


def _live_bounds(observation, rail):
    mins, maxes = [], []
    for rails in observation.surfaces.values():
        reading = rails.get(rail)
        if reading is None:
            continue
        if reading.min_w is not None:
            mins.append(int(reading.min_w))
        if reading.max_w is not None:
            maxes.append(int(reading.max_w))
    return (max(mins) if mins else None, min(maxes) if maxes else None)


def build_targets(requested, safe_bounds, observation):
    target, reasons = {}, {}
    for rail, raw in requested.items():
        bound = safe_bounds[rail]
        safe_min, safe_max = int(bound["min"]), int(bound["max"])
        live_min, live_max = _live_bounds(observation, rail)
        lo = max(safe_min, live_min) if live_min is not None else safe_min
        hi = min(safe_max, live_max) if live_max is not None else safe_max
        if hi < lo:
            lo = hi = max(safe_min, min(safe_max, hi))
        value = max(lo, min(int(raw), hi))
        target[rail] = value
        if value > int(raw):
            reasons[rail] = (
                "live_min"
                if live_min is not None and lo == live_min
                else "safe_min"
            )
        elif value < int(raw):
            reasons[rail] = (
                "live_max"
                if live_max is not None and hi == live_max
                else "safe_max"
            )
    return TargetSet(dict(requested), target, reasons)


def _signature(targets, observation, tolerance):
    values = []
    for surface, rails in observation.surfaces.items():
        for rail, reading in rails.items():
            expected = targets.target.get(rail)
            applied = reading.applied_w
            if expected is None or applied is None:
                continue
            if abs(int(applied) - int(expected)) > tolerance:
                values.append((surface, rail, int(applied), int(expected)))
    return tuple(sorted(values))


def _has_target_readback(targets, observation):
    observed = {
        rail
        for rails in observation.surfaces.values()
        for rail, reading in rails.items()
        if reading.applied_w is not None
    }
    return set(targets.target) <= observed


def _divergence_reason(targets, observation):
    by_rail = {}
    for rails in observation.surfaces.values():
        for rail, reading in rails.items():
            if rail not in targets.target or reading.applied_w is None:
                continue
            by_rail.setdefault(rail, set()).add(int(reading.applied_w))
    if any(len(values) > 1 for values in by_rail.values()):
        return "surface_mismatch"
    return "external_drift"


def _steady_status(targets):
    if not targets.reasons:
        return "in_sync", ""
    reason = next(iter(targets.reasons.values()))
    return "constrained", reason


def _recent_memory(memory, now):
    recent = tuple(
        seen for seen in memory.drift_times
        if now - seen <= CONFLICT_WINDOW_S
    )
    return replace(memory, drift_times=recent), len(recent) >= CONFLICT_COUNT


def decide(
    targets,
    observation,
    memory,
    now,
    tolerance,
    write_only=False,
    force=False,
):
    memory, conflict = _recent_memory(memory, now)
    if write_only:
        if memory.failures:
            status = (
                "rejected"
                if memory.failures > len(RETRY_S)
                else "settling"
            )
            action = "apply" if now >= memory.next_retry_at else "hold"
            return ReconcileDecision(
                action,
                status,
                "write_rejected",
                memory,
                conflict,
            )
        if force or now >= memory.next_retry_at:
            return ReconcileDecision(
                "apply",
                "unverifiable",
                "read_unavailable",
                replace(
                    memory,
                    next_retry_at=now + UNVERIFIABLE_HEARTBEAT_S,
                ),
                conflict,
            )
        return ReconcileDecision(
            "hold",
            "unverifiable",
            "read_unavailable",
            memory,
            conflict,
        )
    if not _has_target_readback(targets, observation):
        if memory.failures:
            status = (
                "rejected"
                if memory.failures > len(RETRY_S)
                else "settling"
            )
            action = "apply" if now >= memory.next_retry_at else "hold"
            return ReconcileDecision(
                action,
                status,
                "write_rejected",
                memory,
                conflict,
            )
        if (
            memory.last_write_at is not None
            and memory.next_retry_at > 0.0
            and now >= memory.next_retry_at
        ):
            return ReconcileDecision(
                "apply",
                "unverifiable",
                "read_unavailable",
                memory,
                conflict,
            )
        return ReconcileDecision(
            "hold",
            "unverifiable",
            "read_unavailable",
            memory,
            conflict,
        )
    signature = _signature(targets, observation, tolerance)
    if not signature:
        status, reason = _steady_status(targets)
        clean = replace(
            memory,
            pending_signature=None,
            pending_since=None,
            failures=0,
            next_retry_at=0.0,
        )
        return ReconcileDecision("hold", status, reason, clean, conflict)
    if memory.failures and now < memory.next_retry_at:
        status = (
            "rejected"
            if memory.failures > len(RETRY_S)
            else "settling"
        )
        return ReconcileDecision(
            "hold",
            status,
            "write_rejected",
            memory,
            conflict,
        )
    if memory.failures and now >= memory.next_retry_at:
        return ReconcileDecision(
            "apply",
            "drift",
            "write_rejected",
            memory,
            conflict,
        )
    reason = _divergence_reason(targets, observation)
    if memory.pending_signature != signature:
        armed = replace(
            memory,
            pending_signature=signature,
            pending_since=now,
        )
        return ReconcileDecision(
            "confirm_again",
            "settling",
            reason,
            armed,
            conflict,
        )
    pending_since = (
        memory.pending_since
        if memory.pending_since is not None
        else now
    )
    if now - pending_since < CONFIRM_S:
        return ReconcileDecision(
            "confirm_again",
            "settling",
            reason,
            memory,
            conflict,
        )
    if (
        memory.last_write_at is not None
        and now - memory.last_write_at < MIN_CORRECTION_S
    ):
        return ReconcileDecision(
            "hold",
            "settling",
            reason,
            memory,
            conflict,
        )
    ready, conflict = _recent_memory(
        replace(memory, drift_times=memory.drift_times + (now,)),
        now,
    )
    return ReconcileDecision("apply", "drift", reason, ready, conflict)


def after_apply(
    targets,
    observation,
    memory,
    now,
    wrote_ok,
    tolerance,
    write_only=False,
):
    memory, conflict = _recent_memory(memory, now)
    if write_only and wrote_ok:
        pending = replace(
            memory,
            pending_signature=None,
            pending_since=None,
            next_retry_at=now + UNVERIFIABLE_HEARTBEAT_S,
            last_write_at=now,
        )
        return ReconcileDecision(
            "verify",
            "unverifiable",
            "read_unavailable",
            pending,
            conflict,
        )
    has_readback = _has_target_readback(targets, observation)
    signature = _signature(targets, observation, tolerance)
    if wrote_ok and has_readback and not signature:
        status, reason = _steady_status(targets)
        clean = replace(
            memory,
            pending_signature=None,
            pending_since=None,
            failures=0,
            next_retry_at=now + VERIFY_S,
            last_write_at=now,
        )
        return ReconcileDecision("verify", status, reason, clean, conflict)
    if wrote_ok and not has_readback:
        pending = replace(
            memory,
            pending_signature=None,
            pending_since=None,
            next_retry_at=now + UNVERIFIABLE_HEARTBEAT_S,
            last_write_at=now,
        )
        return ReconcileDecision(
            "verify",
            "unverifiable",
            "read_unavailable",
            pending,
            conflict,
        )
    failures = memory.failures + 1
    if failures <= len(RETRY_S):
        delay = RETRY_S[failures - 1]
        retry = replace(
            memory,
            failures=failures,
            next_retry_at=now + delay,
            last_write_at=now,
        )
        return ReconcileDecision(
            "retry",
            "settling",
            "write_rejected",
            retry,
            conflict,
        )
    degraded = replace(
        memory,
        failures=failures,
        next_retry_at=now + DEGRADED_RETRY_S,
        last_write_at=now,
    )
    return ReconcileDecision(
        "degrade",
        "rejected",
        "write_rejected",
        degraded,
        conflict,
    )
