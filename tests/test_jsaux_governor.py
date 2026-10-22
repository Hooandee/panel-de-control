from accessories.jsaux_pixel import governor
from accessories.jsaux_pixel.governor import Decision, Governor


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_same_content_is_never_uploaded_twice():
    clock = Clock()
    gov = Governor(clock)
    assert gov.decide("a", "user") is Decision.ALLOW
    gov.record("a", ok=True)
    clock.t += 3600
    assert gov.decide("a", "scheduled") is Decision.DUPLICATE
    assert gov.decide("a", "user") is Decision.DUPLICATE


def test_failed_upload_does_not_count_as_shown():
    gov = Governor(Clock())
    gov.record("a", ok=False)
    assert gov.decide("a", "user") is Decision.ALLOW


def test_automatic_uploads_wait_twenty_seconds_and_live_metrics_a_minute():
    clock = Clock()
    gov = Governor(clock)
    gov.record("a", ok=True, kind="scheduled")
    clock.t += 19
    assert gov.decide("b", "scheduled") is Decision.TOO_SOON
    clock.t += 1
    assert gov.decide("b", "scheduled") is Decision.ALLOW
    gov.record("b", ok=True, kind="live", metric="fps")
    clock.t += 59
    assert gov.decide("c", "live", metric="fps") is Decision.TOO_SOON
    assert gov.decide("c", "live", metric="watts") is Decision.ALLOW
    clock.t += 1
    assert gov.decide("c", "live", metric="fps") is Decision.ALLOW


def test_user_choices_apply_at_once():
    clock = Clock()
    gov = Governor(clock)
    gov.record("a", ok=True, kind="scheduled")
    assert gov.decide("b", "user") is Decision.ALLOW


def test_hourly_and_daily_budgets():
    clock = Clock()
    gov = Governor(clock)
    for n in range(60):
        gov.record(f"s{n}", ok=True, kind="scheduled")
        clock.t += 21
    assert gov.decide("next", "scheduled") is Decision.BUDGET
    assert gov.decide("next", "user") is Decision.ALLOW
    clock.t += 3600
    assert gov.decide("next", "scheduled") is Decision.ALLOW
    for n in range(120):
        gov.record(f"u{n}", ok=True, kind="user")
    assert gov.decide("more", "user") is Decision.BUDGET


def test_daily_budget_caps_automatic_uploads():
    clock = Clock()
    gov = Governor(clock)
    for n in range(600):
        gov.record(f"s{n}", ok=True, kind="scheduled")
        clock.t += 120
    assert gov.decide("next", "scheduled") is Decision.BUDGET


def test_state_survives_a_restart():
    clock = Clock()
    gov = Governor(clock)
    gov.record("a", ok=True, kind="user")
    restored = Governor(clock, gov.snapshot())
    assert restored.decide("a", "user") is Decision.DUPLICATE
    assert restored.stats()["last_hour"] == 1


def test_corrupt_snapshot_starts_clean():
    gov = Governor(Clock(), {"uploads": "nonsense", "last_hash": 5})
    assert gov.decide("a", "user") is Decision.ALLOW


def test_showing_a_firmware_animation_makes_the_last_gif_uploadable_again():
    gov = Governor(Clock())
    gov.record("a", ok=True)
    gov.forget_shown()
    assert gov.decide("a", "user") is Decision.ALLOW


def test_live_gap_counts_the_users_own_upload_of_that_metric():
    clock = Clock()
    gov = Governor(clock)
    gov.record("a", ok=True, kind="user", metric="dashboard")
    clock.t += 5
    assert gov.decide("b", "live", metric="dashboard") is Decision.TOO_SOON
    clock.t += 56
    assert gov.decide("b", "live", metric="dashboard") is Decision.ALLOW


def test_boundaries_keep_a_gap_and_an_hourly_cap_so_a_broken_expiry_cannot_hammer_the_flash():
    clock = [1000.0]
    gov = governor.Governor(lambda: clock[0])
    assert gov.decide("a", "boundary") is governor.Decision.ALLOW
    gov.record("a", ok=True, kind="boundary")
    clock[0] += 5
    assert gov.decide("b", "boundary") is governor.Decision.TOO_SOON
    allowed = 0
    for i in range(200):
        clock[0] += 61
        if gov.decide(f"x{i}", "boundary") is governor.Decision.ALLOW:
            gov.record(f"x{i}", ok=True, kind="boundary")
            allowed += 1
    assert allowed <= 30 * 4


def test_a_daily_ceiling_covers_every_kind_of_write():
    clock = [1000.0]
    gov = governor.Governor(lambda: clock[0])
    allowed = 0
    for i in range(5000):
        clock[0] += 15
        kind = ("user", "boundary", "alert")[i % 3]
        if gov.decide(f"h{i}", kind) is governor.Decision.ALLOW:
            gov.record(f"h{i}", ok=True, kind=kind)
            allowed += 1
        if clock[0] - 1000 > 86400:
            break
    assert allowed <= governor.DAILY_CEILING
