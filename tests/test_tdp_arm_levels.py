
from tdp.arm_levels import ArmPerformanceLevels
from arm_support import BIG, GPU, LITTLE, PRIME, _caps, _thor  # noqa: F401
from arm_support import _policy, _read, _write  # noqa: F401


def test_levels_are_one_to_ten_and_report_unit(tmp_path):
    backend = ArmPerformanceLevels(root=_thor(tmp_path))
    assert backend.supported is True
    assert backend.unit == "level"
    limits = backend.get_limits()
    assert (limits.min_w, limits.max_w, limits.max_ac_w) == (1, 10, 10)


def test_top_level_removes_every_ceiling_including_boost(tmp_path):
    root = _thor(tmp_path)
    result = ArmPerformanceLevels(root=root).set_tdp(10, ac=False)
    assert result.ok is True
    assert result.applied_w == 10
    assert _caps(root) == (2016000, 2803200, 3187200, 680000000)


def test_middle_level_snaps_every_cluster_and_gpu_to_real_steps(tmp_path):
    root = _thor(tmp_path, armada_balanced=False)
    backend = ArmPerformanceLevels(root=root)
    assert backend.set_tdp(6, ac=False).ok is True
    assert _caps(root) == (1459200, 2054400, 2227200, 475000000)
    assert backend.read_applied() == 6


def test_lowest_level_keeps_a_usable_floor(tmp_path):
    root = _thor(tmp_path)
    assert ArmPerformanceLevels(root=root).set_tdp(1, ac=False).ok is True
    assert _caps(root) == (787200, 1056000, 1248000, 220000000)


def test_external_ceilings_read_as_no_level(tmp_path):
    backend = ArmPerformanceLevels(root=_thor(tmp_path))
    assert backend.read_applied() is None


def test_release_lifts_every_ceiling_and_lets_the_system_reapply(tmp_path):
    root = _thor(tmp_path)
    reloads = []
    backend = ArmPerformanceLevels(root=root, on_release=lambda: reloads.append(True))
    backend.set_tdp(3, ac=False)
    assert backend.release() is True
    assert _caps(root) == (2016000, 2803200, 3187200, 680000000)
    assert reloads == [True]


def test_release_after_a_restart_needs_no_memory_of_the_start(tmp_path):
    root = _thor(tmp_path)
    ArmPerformanceLevels(root=root).set_tdp(3, ac=False)
    assert ArmPerformanceLevels(root=root).release() is True
    assert _caps(root) == (2016000, 2803200, 3187200, 680000000)


def _cooling(root, index, kind, state):
    base = f"sys/class/thermal/cooling_device{index}"
    _write(root, f"{base}/type", kind)
    _write(root, f"{base}/cur_state", state)


def test_thermal_throttling_below_the_level_still_reads_as_that_level(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_tdp(10, ac=False)
    _write(root, "sys/devices/system/cpu/cpufreq/policy7/scaling_max_freq", 2476800)
    _cooling(root, 2, "cpufreq-cpu7", 0)
    assert backend.read_applied() is None
    _cooling(root, 2, "cpufreq-cpu7", 4)
    assert backend.read_applied() == 10


def test_level_ten_follows_the_boost_switch(tmp_path):
    root = _thor(tmp_path)
    _write(root, "sys/devices/system/cpu/cpufreq/boost", "0")
    backend = ArmPerformanceLevels(root=root)
    assert backend.set_tdp(10, ac=False).ok is True
    assert _caps(root)[2] == 2956800
    _write(root, "sys/devices/system/cpu/cpufreq/boost", "1")
    assert backend.set_tdp(10, ac=False).ok is True
    assert _caps(root)[2] == 3187200


def test_minimum_frequency_never_stays_above_the_new_ceiling(tmp_path):
    root = _thor(tmp_path)
    _write(root, "sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq", 1555200)
    _write(root, "sys/class/devfreq/3d00000.gpu/min_freq", 475000000)
    assert ArmPerformanceLevels(root=root).set_tdp(1, ac=False).ok is True
    assert _read(root, "sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq") <= 787200
    assert _read(root, "sys/class/devfreq/3d00000.gpu/min_freq") <= 220000000


def test_without_cpufreq_tables_the_backend_is_unsupported(tmp_path):
    assert ArmPerformanceLevels(root=str(tmp_path)).supported is False


def test_level_table_shows_real_frequencies_for_the_slider(tmp_path):
    table = ArmPerformanceLevels(root=_thor(tmp_path)).level_table()
    assert table["6"] == {"cpu_khz": [1459200, 2054400, 2227200], "gpu_mhz": 475}
    assert table["10"] == {"cpu_khz": [2016000, 2803200, 3187200], "gpu_mhz": 680}


def test_levels_are_safe_for_auto(tmp_path):
    backend = ArmPerformanceLevels(root=_thor(tmp_path))
    assert backend.auto_tdp_supported is True
    assert backend.auto_tdp_safe is True
    assert backend.readback is True


def test_a_ceiling_published_late_is_waited_for_not_reported_as_a_mismatch(tmp_path):
    root = _thor(tmp_path, armada_balanced=False)
    node = "sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
    backend = ArmPerformanceLevels(root=root, sleep=lambda _s: None)
    want = backend.ceilings(4)[0]
    real_write = backend._domains[0].write
    pending = []

    def late_write(ceiling):
        ok = real_write(ceiling)
        _write(root, node, 2016000)
        pending.append(ceiling)
        return ok

    def settle(_s):
        if pending:
            _write(root, node, pending.pop())

    backend._domains[0].write = late_write
    backend._sleep = settle
    result = backend.set_tdp(4, False)
    assert result.ok is True
    assert _read(root, node) == want


def test_a_ceiling_that_never_lands_still_reports_the_mismatch(tmp_path):
    root = _thor(tmp_path, armada_balanced=False)
    ticks = iter(range(100))
    backend = ArmPerformanceLevels(root=root, sleep=lambda _s: None, clock=lambda: next(ticks) * 0.1)
    real_write = backend._domains[0].write
    backend._domains[0].write = lambda c: real_write(c) and (_write(
        root, "sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq", 2016000) or True)
    result = backend.set_tdp(4, False)
    assert result.ok is False
    assert result.detail == "readback mismatch"
