import os

from cpu.controls import SmtControl, select_boost


def _write(root, rel, val):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(str(val))
    return p


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
