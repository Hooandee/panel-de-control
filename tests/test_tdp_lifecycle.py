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


def test_check_survives_apply_exception():
    def boom(_on_ac):
        raise RuntimeError("boom")
    ac = {"v": False}
    lm = LifecycleManager(apply_cb=boom, read_wakeup=lambda: 0, read_ac=lambda: ac["v"])
    lm.check(now=0.0)      # first observation
    ac["v"] = True
    lm.check(now=1.0)      # AC change → apply_cb raises; check() must NOT propagate
    # (no assertion needed beyond "did not raise")
