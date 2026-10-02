import os

from cpu.controls import CoreControl
from cpu.info import read_cpu_info


def _cpu(root, idx, core_id, capacity, cluster=0, max_khz=None):
    base = os.path.join(root, "sys/devices/system/cpu", f"cpu{idx}")
    os.makedirs(os.path.join(base, "topology"), exist_ok=True)
    with open(os.path.join(base, "topology", "core_id"), "w") as handle:
        handle.write(str(core_id))
    with open(os.path.join(base, "topology", "cluster_id"), "w") as handle:
        handle.write(str(cluster))
    with open(os.path.join(base, "cpu_capacity"), "w") as handle:
        handle.write(str(capacity))
    if idx:
        with open(os.path.join(base, "online"), "w") as handle:
            handle.write("1")


def _thor(tmp_path, repeated_ids=False):
    root = str(tmp_path)
    layout = [(0, 222, 0), (1, 222, 0), (2, 222, 0), (3, 657, 1), (4, 657, 1),
              (5, 657, 1), (6, 657, 1), (7, 1024, 2)]
    for idx, cap, cluster in layout:
        core_id = (idx - {0: 0, 1: 3, 2: 7}[cluster]) if repeated_ids else idx
        _cpu(root, idx, core_id, cap, cluster=cluster if repeated_ids else 0)
    return root


def _online(root, idx):
    with open(os.path.join(root, "sys/devices/system/cpu", f"cpu{idx}", "online")) as handle:
        return handle.read().strip() == "1"


def test_big_little_sheds_the_weakest_cores_first(tmp_path):
    root = _thor(tmp_path)
    control = CoreControl(root)
    assert control.max_cores == 8
    assert control.set(4) is True
    assert [i for i in range(1, 8) if _online(root, i)] == [3, 4, 7]


def test_repeated_core_ids_across_clusters_still_count_every_core(tmp_path):
    root = _thor(tmp_path, repeated_ids=True)
    assert CoreControl(root).max_cores == 8
    assert read_cpu_info(root)["cores"] == 8


def test_max_frequency_is_the_fastest_cluster(tmp_path):
    root = _thor(tmp_path)
    for policy, khz in ((0, 2016000), (3, 2803200), (7, 3187200)):
        path = os.path.join(root, "sys/devices/system/cpu/cpufreq", f"policy{policy}")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "cpuinfo_max_freq"), "w") as handle:
            handle.write(str(khz))
    assert read_cpu_info(root)["max_khz"] == 3187200


def test_max_frequency_includes_the_boost_step_while_boost_is_off(tmp_path):
    root = _thor(tmp_path)
    path = os.path.join(root, "sys/devices/system/cpu/cpufreq/policy7")
    os.makedirs(path, exist_ok=True)
    for name, value in (("cpuinfo_max_freq", "2956800"), ("scaling_available_frequencies", "595200 2956800"),
                        ("scaling_boost_frequencies", "3187200")):
        with open(os.path.join(path, name), "w") as handle:
            handle.write(value)
    assert read_cpu_info(root)["max_khz"] == 3187200
