import os

import gpu.clock as clock_module

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


def _emulate_amd_sysfs(
    monkeypatch,
    *,
    level="auto",
    window=(800, 2700),
    fail_command=None,
    mismatch_once=False,
    reset_noop=False,
):
    state = {
        "level": level,
        "window": tuple(window),
        "default_window": (200, 2700),
        "pending": list(window),
        "mismatch_once": mismatch_once,
    }

    def od_text():
        lo, hi = state["window"]
        return (
            f"OD_SCLK:\n0: {lo}Mhz\n1: {hi}Mhz\n"
            "OD_RANGE:\nSCLK: 200Mhz 2700Mhz\n"
        )

    def read(path):
        if path.endswith("pp_od_clk_voltage"):
            return od_text()
        if path.endswith("power_dpm_force_performance_level"):
            return state["level"]
        return None

    def write(path, value):
        value = str(value)
        if path.endswith("power_dpm_force_performance_level"):
            state["level"] = value
            return True
        if value == fail_command:
            return False
        if value.startswith("s 0 "):
            state["pending"][0] = int(value.split()[-1])
        elif value.startswith("s 1 "):
            state["pending"][1] = int(value.split()[-1])
        elif value == "c":
            applied = tuple(state["pending"])
            if state["mismatch_once"]:
                state["mismatch_once"] = False
                applied = (applied[0], applied[1] - 50)
            state["window"] = applied
        elif value == "r":
            if not reset_noop:
                state["window"] = state["default_window"]
                state["pending"] = list(state["default_window"])
        return True

    monkeypatch.setattr(clock_module, "read_str", read)
    monkeypatch.setattr(clock_module, "write_str", write)
    return state


def test_amd_supported_and_range(tmp_path):
    root = _amd_tree(str(tmp_path))
    g = AmdGpuClock(root=root)
    assert g.supported is True
    assert g.get_range() == (200, 2700)
    assert g.get() == (800, 2700)


def test_amd_set_switches_to_manual(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path))
    state = _emulate_amd_sysfs(monkeypatch)
    g = AmdGpuClock(root=root)
    assert g.set(1200, 2400) is True
    assert state["level"] == "manual"
    assert state["window"] == (1200, 2400)


def test_amd_partial_write_failure_returns_to_auto(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path))
    state = _emulate_amd_sysfs(monkeypatch, fail_command="s 1 2400")
    g = AmdGpuClock(root=root)

    assert g.set(1200, 2400) is False
    assert state["level"] == "auto"
    assert state["window"] == (800, 2700)
    operation = g.diagnostics()["last_operation"]
    assert operation["ok"] is False
    assert operation["applied"] == {"min_mhz": 800, "max_mhz": 2700}


def test_amd_readback_mismatch_restores_previous_manual_window(
    tmp_path, monkeypatch
):
    root = _amd_tree(str(tmp_path), level="manual")
    state = _emulate_amd_sysfs(
        monkeypatch,
        level="manual",
        mismatch_once=True,
    )
    g = AmdGpuClock(root=root)

    assert g.set(1200, 2400) is False
    assert state["level"] == "manual"
    assert state["window"] == (800, 2700)
    assert g.diagnostics()["last_operation"]["ok"] is False


def test_amd_set_auto_releases(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path), level="manual")
    state = _emulate_amd_sysfs(monkeypatch, level="manual")
    g = AmdGpuClock(root=root)
    assert g.set_auto() is True
    assert state["level"] == "auto"
    assert state["window"] == state["default_window"]


def test_amd_restores_captured_external_manual_mode_and_window(
    tmp_path, monkeypatch
):
    root = _amd_tree(str(tmp_path), level="manual")
    state = _emulate_amd_sysfs(
        monkeypatch,
        level="manual",
        window=(1_200, 2_400),
    )
    backend = AmdGpuClock(root=root)
    snapshot = backend.capture_state()
    assert backend.set(900, 1_800) is True

    assert backend.restore_state(snapshot) is True
    assert state["level"] == "manual"
    assert state["window"] == (1_200, 2_400)


def test_amd_restores_captured_auto_mode_and_full_window(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path), level="auto")
    state = _emulate_amd_sysfs(
        monkeypatch,
        level="auto",
        window=(200, 2_700),
    )
    backend = AmdGpuClock(root=root)
    snapshot = backend.capture_state()
    assert backend.set(900, 1_800) is True

    assert backend.restore_state(snapshot) is True
    assert state["level"] == "auto"
    assert state["window"] == (200, 2_700)


def test_amd_set_auto_resets_the_overdrive_window(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path))
    state = _emulate_amd_sysfs(monkeypatch)
    backend = AmdGpuClock(root=root)
    assert backend.set(1_200, 2_400) is True

    assert backend.set_auto() is True

    assert state["level"] == "auto"
    assert state["window"] == (200, 2_700)
    assert backend.get() == (200, 2_700)


def test_amd_failed_manual_apply_from_auto_resets_overdrive(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path))
    state = _emulate_amd_sysfs(monkeypatch, mismatch_once=True)
    backend = AmdGpuClock(root=root)

    assert backend.set(1_200, 2_400) is False

    assert state["level"] == "auto"
    assert state["window"] == (800, 2_700)
    assert backend.get() == (800, 2_700)


def test_amd_set_auto_rejects_an_unconfirmed_overdrive_reset(
    tmp_path, monkeypatch
):
    root = _amd_tree(str(tmp_path))
    state = _emulate_amd_sysfs(monkeypatch, reset_noop=True)
    backend = AmdGpuClock(root=root)
    assert backend.set(1_200, 2_400) is True

    assert backend.set_auto() is False

    assert state["level"] == "auto"
    assert state["window"] == (1_200, 2_400)
    assert backend.diagnostics()["last_operation"]["reason"] == "reset_mismatch"


def test_amd_absent_unsupported(tmp_path):
    assert AmdGpuClock(root=str(tmp_path)).supported is False


def test_amd_missing_frequency_readback_unsupported(tmp_path):
    dev = "sys/class/drm/card0/device"
    _write(str(tmp_path), f"{dev}/pp_od_clk_voltage", "OD_RANGE:\nSCLK: 200Mhz 2700Mhz\n")
    _write(str(tmp_path), f"{dev}/power_dpm_force_performance_level", "auto")

    assert AmdGpuClock(root=str(tmp_path)).supported is False


def test_amd_unwritable_surface_unsupported(tmp_path, monkeypatch):
    root = _amd_tree(str(tmp_path))
    monkeypatch.setattr(
        clock_module.os,
        "access",
        lambda path, mode: not path.endswith("pp_od_clk_voltage"),
    )

    assert AmdGpuClock(root=root).supported is False


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
    diag = g.diagnostics()
    assert diag["backend"] == "i915"
    assert diag["last_operation"]["requested"] == {
        "min_mhz": 600,
        "max_mhz": 1500,
    }
    assert diag["last_operation"]["applied"] == {
        "min_mhz": 600,
        "max_mhz": 1500,
    }
    assert diag["last_operation"]["ok"] is True


def test_intel_set_auto_restores_full_range(tmp_path):
    root = _intel_tree(str(tmp_path), cur_min=600, cur_max=1200, rpn=300, rp0=2000)
    g = IntelGpuClock(root=root)
    assert g.set_auto() is True
    assert g.get() == (300, 2000)


def test_intel_restores_captured_external_window(tmp_path):
    root = _intel_tree(str(tmp_path), cur_min=600, cur_max=1_500)
    backend = IntelGpuClock(root=root)
    snapshot = backend.capture_state()
    assert backend.set(900, 1_200) is True

    assert backend.restore_state(snapshot) is True
    assert backend.get() == (600, 1_500)


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


def test_xe_partial_write_failure_restores_original_window(
    tmp_path, monkeypatch
):
    root = _xe_tree(
        str(tmp_path),
        cur_min=300,
        cur_max=500,
        rpn=300,
        rp0=2_000,
    )
    backend = XeGpuClock(root=root)
    real_write = clock_module.write_str

    def fail_second_write(path, value):
        if path.endswith("/min_freq") and int(value) == 600:
            return False
        return real_write(path, value)

    monkeypatch.setattr(clock_module, "write_str", fail_second_write)

    result = backend.set(600, 1_500)

    assert result is False
    assert backend.get() == (300, 500)
    operation = backend.diagnostics()["last_operation"]
    assert operation["ok"] is False
    assert operation["applied"] == {
        "min_mhz": 300,
        "max_mhz": 500,
    }


def test_xe_absent_unsupported(tmp_path):
    assert XeGpuClock(root=str(tmp_path)).supported is False


# ---- selection ----

def test_select_xe_for_intel_device(tmp_path):
    root = _xe_tree(str(tmp_path))

    class Dev:
        vendor = "intel"

    assert isinstance(select_gpu_clock(Dev(), root=root), XeGpuClock)


def test_incomplete_xe_surface_falls_back_to_complete_i915(tmp_path):
    root = str(tmp_path)
    xe = "sys/class/drm/card0/device/tile0/gt0/freq0"
    _write(root, f"{xe}/max_freq", 2_000)
    i915 = "sys/class/drm/card1"
    _write(root, f"{i915}/gt_min_freq_mhz", 300)
    _write(root, f"{i915}/gt_max_freq_mhz", 2_000)
    _write(root, f"{i915}/gt_RPn_freq_mhz", 300)
    _write(root, f"{i915}/gt_RP0_freq_mhz", 2_000)

    class IntelDevice:
        vendor = "intel"

    backend = select_gpu_clock(IntelDevice(), root=root)

    assert isinstance(backend, IntelGpuClock)
    assert backend.supported is True
    assert backend.get_range() == (300, 2_000)
    assert backend.get() == (300, 2_000)
    assert backend.diagnostics()["selection"] == [
        {
            "backend": "xe",
            "supported": False,
            "range_available": False,
            "applied_available": False,
            "reason": "incomplete_or_unwritable",
        },
        {
            "backend": "i915",
            "supported": True,
            "range_available": True,
            "applied_available": True,
            "reason": "selected",
        },
    ]


def test_i915_skips_incomplete_card_before_complete_card(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/class/drm/card0/gt_max_freq_mhz", 1_000)
    complete = "sys/class/drm/card1"
    _write(root, f"{complete}/gt_min_freq_mhz", 300)
    _write(root, f"{complete}/gt_max_freq_mhz", 2_000)
    _write(root, f"{complete}/gt_RPn_freq_mhz", 300)
    _write(root, f"{complete}/gt_RP0_freq_mhz", 2_000)

    backend = IntelGpuClock(root=root)

    assert backend.supported is True
    assert backend.get_range() == (300, 2_000)
    assert backend.get() == (300, 2_000)


def test_xe_does_not_fall_back_from_primary_to_media_gt(tmp_path):
    root = str(tmp_path)
    incomplete = "sys/class/drm/card0/device/tile0/gt0/freq0"
    _write(root, f"{incomplete}/max_freq", 1_000)
    complete = "sys/class/drm/card0/device/tile0/gt1/freq0"
    _write(root, f"{complete}/min_freq", 300)
    _write(root, f"{complete}/max_freq", 2_000)
    _write(root, f"{complete}/rpn_freq", 300)
    _write(root, f"{complete}/rp0_freq", 2_000)

    backend = XeGpuClock(root=root)

    assert backend.supported is False
    assert backend.get_range() is None
    assert backend.get() is None


def test_intel_device_never_selects_amdgpu_fallback(tmp_path):
    root = _amd_tree(str(tmp_path))

    class IntelDevice:
        vendor = "intel"

    backend = select_gpu_clock(IntelDevice(), root=root)

    assert isinstance(backend, NullGpuClock)
    assert backend.supported is False
    assert [row["backend"] for row in backend.diagnostics()["selection"]] == [
        "xe",
        "i915",
    ]


def test_select_amd_for_amd_device(tmp_path):
    root = _amd_tree(str(tmp_path))

    class Dev:
        vendor = "amd"

    assert isinstance(select_gpu_clock(Dev(), root=root), AmdGpuClock)


def test_select_null_when_nothing(tmp_path):
    class Dev:
        vendor = "amd"

    assert isinstance(select_gpu_clock(Dev(), root=str(tmp_path)), NullGpuClock)


def test_null_diagnostics_are_honest():
    diag = NullGpuClock().diagnostics()
    assert diag == {
        "backend": "none",
        "supported": False,
        "range": None,
        "applied": None,
        "last_operation": None,
        "selection": [],
    }
