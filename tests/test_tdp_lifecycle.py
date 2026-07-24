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
    ac = {"v": True}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(("apply", on_ac)),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_ac=lambda: ac["v"])
    lm.check(now=100.0)          # first observation, no event
    assert events == []
    wc["v"] = 6                  # a suspend/resume bumped wakeup_count
    lm.check(now=101.0)          # detected, but within delay → not yet
    assert events == []
    lm.check(now=105.5)          # >= 101+4 → re-apply fires once
    assert events == [("apply", True)]
    lm.check(now=106.0)          # no repeat
    assert events == [("apply", True)]


def test_resume_re_asserts_after_firmware_settles():
    # On resume the Lenovo firmware reverts ppt to its default (a Legion Go 2 wakes at
    # ~30 W); a single re-apply can land before that reset and be lost. Resume schedules
    # the base delay + follow-ups so the setpoint is re-asserted once the firmware settles.
    events = []
    wc = {"v": 5}
    lm = LifecycleManager(apply_cb=lambda on_ac: events.append(on_ac),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_ac=lambda: False)
    lm.check(now=100.0)          # first observation
    wc["v"] = 6                  # a suspend/resume bumped wakeup_count
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
    lm = LifecycleManager(apply_cb=lambda ac: full.append(ac),
                          reassert_cb=lambda ac: light.append(ac),
                          wakeup_delay=4.0,
                          read_wakeup=lambda: wc["v"],
                          read_ac=lambda: False)
    lm.check(now=0.0)
    wc["v"] = 1
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
    # (no assertion needed beyond "did not raise")
