import os

from lifecycle import LifecycleManager, read_on_ac


def _mk_ps(root, name, type_, online):
    d = os.path.join(root, "sys/class/power_supply", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "type"), "w") as f:
        f.write(type_)
    with open(os.path.join(d, "online"), "w") as f:
        f.write(online)


def test_read_on_ac_true_when_mains_online(tmp_path):
    root = str(tmp_path)
    _mk_ps(root, "ACAD", "Mains", "1")
    _mk_ps(root, "BAT0", "Battery", "")
    assert read_on_ac(root=root) is True


def test_read_on_ac_false_when_mains_offline(tmp_path):
    root = str(tmp_path)
    _mk_ps(root, "AC0", "Mains", "0")
    assert read_on_ac(root=root) is False


def test_read_on_ac_false_when_no_supply(tmp_path):
    assert read_on_ac(root=str(tmp_path)) is False


def test_reapplies_after_wakeup_delay():
    events = []
    wc = {"v": 5}
    suspended = {"v": 0.0}
    ac = {"v": True}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(("apply", on_ac)),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_suspend=lambda: suspended["v"],
                          read_ac=lambda: ac["v"])
    lm.check(now=100.0)          # first observation, no event
    assert events == []
    wc["v"] = 6                  # a suspend/resume bumped wakeup_count
    suspended["v"] = 10.0
    lm.check(now=101.0)          # detected, but within delay → not yet
    assert events == []
    lm.check(now=105.5)          # >= 101+4 → re-apply fires once
    assert events == [("apply", True)]
    lm.check(now=106.0)          # no repeat
    assert events == [("apply", True)]


def test_awake_wakeup_events_do_not_schedule_resume_reapply():
    events = []
    wakeup = {"value": 0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(("apply", on_ac)),
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: 0.0,
        read_ac=lambda: False,
    )

    for now in range(0, 21, 2):
        wakeup["value"] += 1
        manager.check(now=float(now))

    assert events == []


def test_awake_wakeup_events_leave_bounded_diagnostics():
    diagnostics = []
    wakeup = {"value": 0}
    manager = LifecycleManager(
        apply_cb=lambda _on_ac: None,
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: 0.0,
        read_ac=lambda: False,
        event_cb=diagnostics.append,
    )
    manager.check(now=0.0)

    for now in range(2, 18, 2):
        wakeup["value"] += 1
        manager.check(now=float(now))

    ignored = [
        event
        for event in diagnostics
        if event["event"] == "wakeup_change_ignored"
    ]
    assert [event["ignored_count"] for event in ignored] == [1, 2, 4, 8]
    assert all(
        event["reason"] == "suspend_delta_below_threshold"
        for event in ignored
    )
    assert manager.diagnostics() == {
        "suspend_clock_available": True,
        "resume_count": 0,
        "ignored_wakeup_changes": 8,
        "ac_transition_count": 0,
        "apply_failures": 0,
        "last_apply_failure": None,
        "poll_failures": 0,
        "last_poll_failure": None,
        "pending_full_reapplies": 0,
        "pending_tdp_reasserts": 0,
        "last_event": ignored[-1],
    }


def test_unavailable_suspend_clock_rejects_wakeup_change_honestly():
    diagnostics = []
    events = []
    wakeup = {"value": 0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: None,
        read_ac=lambda: False,
        event_cb=diagnostics.append,
    )
    manager.check(now=0.0)
    wakeup["value"] = 1

    manager.check(now=2.0)

    assert events == []
    assert diagnostics[-1] == {
        "event": "wakeup_change_ignored",
        "reason": "suspend_clock_unavailable",
        "ignored_count": 1,
    }
    assert manager.diagnostics()["suspend_clock_available"] is False


def test_suspend_delta_without_wakeup_change_is_not_a_resume():
    events = []
    suspended = {"value": 0.0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: 5,
        read_suspend=lambda: suspended["value"],
        read_ac=lambda: False,
    )
    manager.check(now=0.0)
    suspended["value"] = 10.0

    manager.check(now=2.0)
    manager.check(now=20.0)

    assert events == []
    assert manager.diagnostics()["resume_count"] == 0


def test_delayed_wakeup_count_still_pairs_with_suspend_delta():
    events = []
    wakeup = {"value": 5}
    suspended = {"value": 0.0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: suspended["value"],
        read_ac=lambda: False,
        wakeup_delay=0.0,
    )
    manager.check(now=0.0)
    suspended["value"] = 10.0
    manager.check(now=2.0)
    wakeup["value"] = 6

    manager.check(now=4.0)

    assert events == [False]
    assert manager.diagnostics()["resume_count"] == 1


def test_stale_suspend_evidence_does_not_pair_with_late_wakeup_change():
    events = []
    wakeup = {"value": 5}
    suspended = {"value": 0.0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: suspended["value"],
        read_ac=lambda: False,
        wakeup_delay=0.0,
    )
    manager.check(now=0.0)
    suspended["value"] = 10.0
    manager.check(now=2.0)
    manager.check(now=3600.0)
    wakeup["value"] = 6

    manager.check(now=3602.0)

    assert events == []
    assert manager.diagnostics()["resume_count"] == 0


def test_stale_suspend_evidence_expires_when_next_poll_has_wakeup_change():
    events = []
    diagnostics = []
    wakeup = {"value": 5}
    suspended = {"value": 0.0}
    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: suspended["value"],
        read_ac=lambda: False,
        wakeup_delay=0.0,
        event_cb=diagnostics.append,
    )
    manager.check(now=0.0)
    suspended["value"] = 10.0
    manager.check(now=2.0)
    wakeup["value"] = 6

    manager.check(now=3602.0)

    assert events == []
    assert manager.diagnostics()["resume_count"] == 0
    assert diagnostics[-1] == {
        "event": "wakeup_change_ignored",
        "reason": "stale_suspend_evidence",
        "ignored_count": 1,
    }


def test_suspend_reader_failure_keeps_ac_handling_and_records_source():
    diagnostics = []
    events = []
    ac = {"value": False}

    def broken_suspend_reader():
        raise OSError("clock unavailable")

    manager = LifecycleManager(
        apply_cb=lambda on_ac: events.append(on_ac),
        read_wakeup=lambda: 0,
        read_suspend=broken_suspend_reader,
        read_ac=lambda: ac["value"],
        event_cb=diagnostics.append,
    )
    manager.check(now=0.0)
    ac["value"] = True

    manager.check(now=2.0)

    assert events == [True]
    assert [
        event["failure_count"]
        for event in diagnostics
        if event["event"] == "poll_failed"
    ] == [1, 2]
    assert manager.diagnostics()["last_poll_failure"] == {
        "stage": "read_suspend",
        "error": "OSError",
        "failure_count": 2,
    }


def test_confirmed_resume_records_detection_evidence():
    diagnostics = []
    wakeup = {"value": 5}
    suspended = {"value": 0.0}
    manager = LifecycleManager(
        apply_cb=lambda _on_ac: None,
        read_wakeup=lambda: wakeup["value"],
        read_suspend=lambda: suspended["value"],
        read_ac=lambda: True,
        event_cb=diagnostics.append,
    )
    manager.check(now=0.0)
    wakeup["value"] = 6
    suspended["value"] = 3.25

    manager.check(now=2.0)

    assert diagnostics[-1] == {
        "event": "resume_detected",
        "suspend_seconds": 3.25,
        "full_delay_seconds": 4.0,
        "tdp_settle_retries": 3,
    }
    assert manager.diagnostics()["resume_count"] == 1


def test_resume_re_asserts_after_firmware_settles():
    # On resume the Lenovo firmware reverts ppt to its default (a Legion Go 2 wakes at
    # ~30 W); a single re-apply can land before that reset and be lost. Resume schedules
    # the base delay + follow-ups so the setpoint is re-asserted once the firmware settles.
    events = []
    wc = {"v": 5}
    suspended = {"v": 0.0}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(on_ac),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_suspend=lambda: suspended["v"],
                          read_ac=lambda: False)
    lm.check(now=100.0)          # first observation
    wc["v"] = 6                  # a suspend/resume bumped wakeup_count
    suspended["v"] = 10.0
    lm.check(now=101.0)          # detected → schedule base (105) + settle retries
    assert events == []
    lm.check(now=105.0)          # base re-apply (101 + 4)
    lm.check(now=107.0)          # +2s settle
    lm.check(now=110.0)          # +5s settle
    lm.check(now=114.0)          # +9s settle
    assert events == [False, False, False, False]
    lm.check(now=120.0)          # window elapsed → no more
    assert events == [False, False, False, False]


def test_resume_base_is_full_reapply_and_retries_are_tdp_only():
    # The base resume re-apply runs the full callback (the firmware may drop color/HDR/fans
    # too); the settle-retries use the lighter TDP-only callback so a wake doesn't re-run
    # the whole re-apply four times.
    full = []
    light = []
    wc = {"v": 0}
    suspended = {"v": 0.0}
    lm = LifecycleManager(apply_cb=lambda ac: full.append(ac),
                          reassert_cb=lambda ac: light.append(ac),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_suspend=lambda: suspended["v"],
                          read_ac=lambda: False)
    lm.check(now=0.0)
    wc["v"] = 1
    suspended["v"] = 10.0
    lm.check(now=1.0)            # resume detected
    lm.check(now=5.0)            # base (1 + 4) → FULL only
    assert (full, light) == ([False], [])
    lm.check(now=7.0)           # 5 + 2 → light
    lm.check(now=10.0)          # 5 + 5 → light
    lm.check(now=14.0)          # 5 + 9 → light
    assert full == [False]                       # full ran exactly once
    assert light == [False, False, False]        # three TDP-only re-asserts


def test_reapplies_on_ac_transition():
    events = []
    ac = {"v": False}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(on_ac),
                          read_wakeup=lambda: 0, read_ac=lambda: ac["v"])
    lm.check(now=0.0)            # first observation
    ac["v"] = True              # plugged in
    lm.check(now=1.0)
    assert events == [True]
    lm.check(now=2.0)           # no change → no event
    assert events == [True]


def test_ac_transition_re_asserts_after_firmware_settles():
    # On unplug the ASUS firmware briefly reverts to ~12 W; a single re-apply landing
    # mid-transition can be lost. The transition fires now + 2 follow-ups (at +2s, +4s),
    # re-reading AC live, so the setpoint is re-asserted once the firmware settles.
    events = []
    ac = {"v": True}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(on_ac),
                          read_wakeup=lambda: 0, read_ac=lambda: ac["v"])
    lm.check(now=0.0)           # first observation, on charger
    ac["v"] = False            # unplug
    lm.check(now=1.0)          # immediate re-apply
    assert events == [False]
    lm.check(now=2.5)          # no follow-up due yet (first at 1.0+2.0=3.0)
    assert events == [False]
    lm.check(now=3.0)          # +2s follow-up
    lm.check(now=5.0)          # +4s follow-up
    assert events == [False, False, False]


def test_check_survives_apply_exception():
    def boom(_on_ac):
        raise RuntimeError("boom")
    ac = {"v": False}
    lm = LifecycleManager(apply_cb=boom, read_wakeup=lambda: 0, read_ac=lambda: ac["v"])
    lm.check(now=0.0)      # first observation
    ac["v"] = True
    lm.check(now=1.0)      # AC change → apply_cb raises; check() must NOT propagate
    diagnostics = lm.diagnostics()
    assert diagnostics["ac_transition_count"] == 1
    assert diagnostics["apply_failures"] == 1
    assert diagnostics["last_apply_failure"] == {
        "operation": "ac-full-reapply",
        "on_ac": True,
        "error": "RuntimeError",
        "failure_count": 1,
    }
