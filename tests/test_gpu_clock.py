import os

from gpu.clock import (
    AmdGpuClock,
    IntelGpuClock,
    NullGpuClock,
    XeGpuClock,
    parse_od_range,
    parse_od_sclk,
    sclk_commands,
    select_gpu_clock,
)

# A realistic amdgpu APU pp_od_clk_voltage dump.
OD_TEXT = """OD_SCLK:
0: 800Mhz
1: 2700Mhz
OD_RANGE:
SCLK:     200Mhz       2700Mhz
"""


def _write(root, rel, val):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(str(val))
    return p


# ---- pure parsing / command building ----

def test_parse_od_range_sclk():
    assert parse_od_range(OD_TEXT) == (200, 2700)


def test_parse_od_range_missing():
    assert parse_od_range("garbage") is None


def test_parse_od_sclk_current():
    assert parse_od_sclk(OD_TEXT) == (800, 2700)


def test_sclk_commands_min_max_then_commit():
    assert sclk_commands(1200, 2400) == ["s 0 1200", "s 1 2400", "c"]


# ---- AMD backend (amdgpu OD) ----

def _amd_tree(root, level="auto"):
    dev = "sys/class/drm/card0/device"
    _write(root, f"{dev}/pp_od_clk_voltage", OD_TEXT)
    _write(root, f"{dev}/power_dpm_force_performance_level", level)
    return root


def test_amd_supported_and_range(tmp_path):
    root = _amd_tree(str(tmp_path))
    g = AmdGpuClock(root=root)
    assert g.supported is True
    assert g.get_range() == (200, 2700)
    assert g.get() == (800, 2700)


def test_amd_set_switches_to_manual(tmp_path):
    root = _amd_tree(str(tmp_path))
    g = AmdGpuClock(root=root)
    assert g.set(1200, 2400) is True
    lvl = os.path.join(root, "sys/class/drm/card0/device/power_dpm_force_performance_level")
    with open(lvl) as f:
        assert f.read().strip() == "manual"


def test_amd_set_auto_releases(tmp_path):
    root = _amd_tree(str(tmp_path), level="manual")
    g = AmdGpuClock(root=root)
    assert g.set_auto() is True
    lvl = os.path.join(root, "sys/class/drm/card0/device/power_dpm_force_performance_level")
    with open(lvl) as f:
        assert f.read().strip() == "auto"


def test_amd_absent_unsupported(tmp_path):
    assert AmdGpuClock(root=str(tmp_path)).supported is False


# ---- Intel backend (i915 gt_*_freq_mhz) ----

def _intel_tree(root, cur_min=300, cur_max=2000, rpn=300, rp0=2000):
    d = "sys/class/drm/card0"
    _write(root, f"{d}/gt_min_freq_mhz", cur_min)
    _write(root, f"{d}/gt_max_freq_mhz", cur_max)
    _write(root, f"{d}/gt_RPn_freq_mhz", rpn)
    _write(root, f"{d}/gt_RP0_freq_mhz", rp0)
    return root


def test_intel_reads_range_and_current(tmp_path):
    root = _intel_tree(str(tmp_path))
    g = IntelGpuClock(root=root)
    assert g.supported is True
    assert g.get_range() == (300, 2000)
    assert g.get() == (300, 2000)


def test_intel_set_writes_min_max(tmp_path):
    root = _intel_tree(str(tmp_path))
    g = IntelGpuClock(root=root)
    assert g.set(600, 1500) is True
    assert g.get() == (600, 1500)


def test_intel_set_auto_restores_full_range(tmp_path):
    root = _intel_tree(str(tmp_path), cur_min=600, cur_max=1200, rpn=300, rp0=2000)
    g = IntelGpuClock(root=root)
    assert g.set_auto() is True
    assert g.get() == (300, 2000)


# ---- Intel Xe backend (Lunar Lake / MSI Claw: tile*/gt*/freq0/*_freq) ----

def _xe_tree(root, cur_min=300, cur_max=2000, rpn=300, rp0=2000):
    # gt0 = render GT (what we control); gt1 = media, given different values to
    # ensure the backend targets gt0.
    d0 = "sys/class/drm/card0/device/tile0/gt0/freq0"
    _write(root, f"{d0}/min_freq", cur_min)
    _write(root, f"{d0}/max_freq", cur_max)
    _write(root, f"{d0}/rpn_freq", rpn)
    _write(root, f"{d0}/rp0_freq", rp0)
    d1 = "sys/class/drm/card0/device/tile0/gt1/freq0"
    _write(root, f"{d1}/min_freq", 111)
    _write(root, f"{d1}/max_freq", 999)
    _write(root, f"{d1}/rpn_freq", 111)
    _write(root, f"{d1}/rp0_freq", 999)
    return root


def test_xe_reads_range_and_current(tmp_path):
    root = _xe_tree(str(tmp_path))
    g = XeGpuClock(root=root)
    assert g.supported is True
    assert g.get_range() == (300, 2000)
    assert g.get() == (300, 2000)


def test_xe_targets_gt0_not_gt1(tmp_path):
    # gt1 has (111, 999); the backend must control gt0 (the render GT).
    g = XeGpuClock(root=_xe_tree(str(tmp_path)))
    assert g.get() == (300, 2000)


def test_xe_set_writes_min_max(tmp_path):
    g = XeGpuClock(root=_xe_tree(str(tmp_path)))
    assert g.set(600, 1500) is True
    assert g.get() == (600, 1500)


def test_xe_set_auto_restores_full_range(tmp_path):
    g = XeGpuClock(root=_xe_tree(str(tmp_path), cur_min=600, cur_max=1200, rpn=300, rp0=2000))
    assert g.set_auto() is True
    assert g.get() == (300, 2000)


def test_xe_absent_unsupported(tmp_path):
    assert XeGpuClock(root=str(tmp_path)).supported is False


# ---- selection ----

def test_select_xe_for_intel_device(tmp_path):
    root = _xe_tree(str(tmp_path))

    class Dev:
        vendor = "intel"

    assert isinstance(select_gpu_clock(Dev(), root=root), XeGpuClock)


def test_select_amd_for_amd_device(tmp_path):
    root = _amd_tree(str(tmp_path))

    class Dev:
        vendor = "amd"

    assert isinstance(select_gpu_clock(Dev(), root=root), AmdGpuClock)


def test_select_null_when_nothing(tmp_path):
    class Dev:
        vendor = "amd"

    assert isinstance(select_gpu_clock(Dev(), root=str(tmp_path)), NullGpuClock)
