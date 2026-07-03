import os

from cpu.controls import CoreControl, SmtControl, select_boost


def _write(root, rel, val):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(str(val))
    return p


def _make_cpu_tree(root, cores, smt=False):
    """Build a synthetic cpu tree with `cores` physical cores (core_id 0..cores-1).
    cpu0 has NO online node (kernel never lets you offline it). With smt=True each
    core has a second logical cpu (sibling sharing the core_id), all starting online."""
    base = "sys/devices/system/cpu"
    idx = 0
    threads = 2 if smt else 1
    for cid in range(cores):
        for _ in range(threads):
            _write(root, f"{base}/cpu{idx}/topology/core_id", cid)
            if idx != 0:  # cpu0 can't be offlined → no online node
                _write(root, f"{base}/cpu{idx}/online", "1")
            idx += 1


# ---- SMT ----

def test_smt_reads_and_toggles(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/devices/system/cpu/smt/control", "on")
    smt = SmtControl(root=root)
    assert smt.supported is True
    assert smt.enabled() is True
    assert smt.set(False) is True
    assert smt.enabled() is False  # wrote "off"
    assert smt.set(True) is True
    assert smt.enabled() is True


def test_smt_notsupported(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/devices/system/cpu/smt/control", "notsupported")
    smt = SmtControl(root=root)
    assert smt.supported is False


def test_smt_absent(tmp_path):
    smt = SmtControl(root=str(tmp_path))
    assert smt.supported is False
    assert smt.set(False) is False


# ---- Boost: AMD (cpufreq/boost, 1=on) ----

def test_amd_boost(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/devices/system/cpu/cpufreq/boost", "1")
    b = select_boost(root=root)
    assert b.supported is True
    assert b.enabled() is True
    assert b.set(False) is True
    assert b.enabled() is False
    assert b.set(True) is True
    assert b.enabled() is True


# ---- Boost: Intel (intel_pstate/no_turbo, inverted) ----

def test_intel_boost_inverted(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/devices/system/cpu/intel_pstate/no_turbo", "0")  # 0 => boost ON
    b = select_boost(root=root)
    assert b.supported is True
    assert b.enabled() is True  # no_turbo=0
    assert b.set(False) is True  # disable boost -> no_turbo=1
    assert b.enabled() is False
    with open(os.path.join(root, "sys/devices/system/cpu/intel_pstate/no_turbo")) as f:
        assert f.read().strip() == "1"


def test_amd_preferred_over_intel(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/devices/system/cpu/cpufreq/boost", "1")
    _write(root, "sys/devices/system/cpu/intel_pstate/no_turbo", "0")
    b = select_boost(root=root)
    from cpu.controls import AmdBoost
    assert isinstance(b, AmdBoost)


def test_boost_absent_is_null(tmp_path):
    b = select_boost(root=str(tmp_path))
    assert b.supported is False
    assert b.set(True) is False


# ---- Active core count (cpuN/online) ----

def test_core_control_reads_topology(tmp_path):
    root = str(tmp_path)
    _make_cpu_tree(root, cores=4)
    cc = CoreControl(root=root)
    assert cc.supported is True
    assert cc.max_cores == 4
    assert cc.active() == 4


def test_core_control_offlines_and_onlines(tmp_path):
    root = str(tmp_path)
    _make_cpu_tree(root, cores=4)
    cc = CoreControl(root=root)
    assert cc.set(2) is True
    assert cc.active() == 2
    # the two higher cores went offline, cpu0's core stays
    assert cc.set(4) is True
    assert cc.active() == 4


def test_core_control_never_offlines_cpu0_core(tmp_path):
    root = str(tmp_path)
    _make_cpu_tree(root, cores=4)
    cc = CoreControl(root=root)
    cc.set(1)             # minimum
    assert cc.active() == 1  # cpu0's core is always kept
    cc.set(0)             # below min clamps to 1, not 0
    assert cc.active() == 1


def test_core_control_counts_smt_core_once(tmp_path):
    root = str(tmp_path)
    _make_cpu_tree(root, cores=4, smt=True)  # 8 logical, 4 physical
    cc = CoreControl(root=root)
    assert cc.max_cores == 4
    assert cc.set(2) is True
    assert cc.active() == 2  # a core with either sibling online counts once


def test_core_control_unsupported_single_core(tmp_path):
    root = str(tmp_path)
    _make_cpu_tree(root, cores=1)
    cc = CoreControl(root=root)
    assert cc.supported is False  # nothing to toggle
    assert cc.set(1) is False
