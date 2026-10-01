import os

from tdp.arm_levels import ArmPerformanceLevels

LITTLE = "307200 441600 556800 672000 787200 902400 1017600 1113600 1228800 1344000 1459200 1555200 1670400 1785600 1900800 2016000"
BIG = "499200 614400 729600 844800 940800 1056000 1171200 1286400 1401600 1536000 1651200 1785600 1920000 2054400 2188800 2323200 2457600 2592000 2707200 2803200"
PRIME = "595200 729600 864000 998400 1132800 1248000 1363200 1478400 1593600 1708800 1843200 1977600 2092800 2227200 2342400 2476800 2592000 2726400 2841600 2956800"
GPU = "220000000 295000000 348000000 401000000 475000000 550000000 615000000 680000000"


def _write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _read(root, rel):
    with open(os.path.join(root, rel)) as handle:
        return int(handle.read())


def _policy(root, number, table, boost="", current_max=None):
    base = f"sys/devices/system/cpu/cpufreq/policy{number}"
    values = [int(v) for v in table.split()] + [int(v) for v in boost.split()]
    _write(root, f"{base}/scaling_available_frequencies", table)
    _write(root, f"{base}/scaling_boost_frequencies", boost)
    _write(root, f"{base}/cpuinfo_min_freq", min(values))
    _write(root, f"{base}/cpuinfo_max_freq", max(values))
    _write(root, f"{base}/scaling_min_freq", min(values))
    _write(root, f"{base}/scaling_max_freq", current_max or max(values))
    return base


def _thor(tmp_path, armada_balanced=True):
    root = str(tmp_path)
    _policy(root, 0, LITTLE, current_max=1555200 if armada_balanced else None)
    _policy(root, 3, BIG, current_max=2054400 if armada_balanced else None)
    _policy(root, 7, PRIME, "3187200", current_max=2092800 if armada_balanced else None)
    gpu = "sys/class/devfreq/3d00000.gpu"
    _write(root, f"{gpu}/available_frequencies", GPU)
    _write(root, f"{gpu}/min_freq", 220000000)
    _write(root, f"{gpu}/max_freq", 680000000)
    _write(root, f"{gpu}/governor", "simple_ondemand")
    return root


def _caps(root):
    return (
        _read(root, "sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"),
        _read(root, "sys/devices/system/cpu/cpufreq/policy3/scaling_max_freq"),
        _read(root, "sys/devices/system/cpu/cpufreq/policy7/scaling_max_freq"),
        _read(root, "sys/class/devfreq/3d00000.gpu/max_freq"),
    )


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


def test_release_restores_the_ceilings_found_before_control(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_tdp(3, ac=False)
    backend.set_tdp(8, ac=False)
    assert backend.release() is True
    assert _caps(root) == (1555200, 2054400, 2092800, 680000000)


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
