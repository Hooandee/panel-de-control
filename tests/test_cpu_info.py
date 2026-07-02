import os

from cpu.info import read_cpu_info, read_cpu_model


def _cpu_base(root):
    d = os.path.join(root, "sys/devices/system/cpu")
    os.makedirs(d, exist_ok=True)
    return d


def _write(path, val):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(val))


def _core(root, cpu, core_id):
    _write(os.path.join(root, "sys/devices/system/cpu", f"cpu{cpu}", "topology", "core_id"), core_id)


def test_reads_cores_threads_and_freq(tmp_path):
    root = str(tmp_path)
    base = _cpu_base(root)
    # 4 threads over 2 physical cores (SMT): cpu0/cpu2 = core 0, cpu1/cpu3 = core 1
    _core(root, 0, 0)
    _core(root, 1, 1)
    _core(root, 2, 0)
    _core(root, 3, 1)
    _write(os.path.join(base, "present"), "0-3")
    _write(os.path.join(base, "cpufreq/policy0/base_frequency"), "3300000")
    _write(os.path.join(base, "cpufreq/policy0/cpuinfo_max_freq"), "5100000")

    info = read_cpu_info(root=root)
    assert info["cores"] == 2
    assert info["threads"] == 4
    assert info["base_khz"] == 3300000
    assert info["max_khz"] == 5100000


def test_no_hyperthreading_threads_equals_cores(tmp_path):
    # Lunar Lake (MSI Claw): no HT → present count == core count, not cores×2.
    root = str(tmp_path)
    base = _cpu_base(root)
    _core(root, 0, 0)
    _core(root, 1, 1)
    _write(os.path.join(base, "present"), "0-1")
    info = read_cpu_info(root=root)
    assert info["cores"] == 2
    assert info["threads"] == 2


def test_missing_freq_is_none(tmp_path):
    root = str(tmp_path)
    _core(root, 0, 0)
    info = read_cpu_info(root=root)
    assert info["cores"] == 1
    assert info["base_khz"] is None
    assert info["max_khz"] is None


def test_empty_sysfs_all_none(tmp_path):
    info = read_cpu_info(root=str(tmp_path))
    assert info["cores"] is None
    assert info["base_khz"] is None
    assert info["max_khz"] is None


def _write_cpuinfo(root, body):
    p = os.path.join(root, "proc", "cpuinfo")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(body)


def test_cpu_model_reads_and_strips_trademark_noise(tmp_path):
    # The real silicon name — shown in the DeviceHeader instead of a hardcoded
    # guess so it's never misleading (e.g. Legion Go 2 = "Ryzen Z2 Extreme", NOT
    # the Ally X's "Ryzen AI Z2 Extreme"). (R)/(TM) noise is stripped.
    root = str(tmp_path)
    _write_cpuinfo(root, "processor\t: 0\nmodel name\t: Intel(R) Core(TM) Ultra 7 258V\nflags\t: fpu\n")
    assert read_cpu_model(root=root) == "Intel Core Ultra 7 258V"


def test_cpu_model_amd_untouched(tmp_path):
    root = str(tmp_path)
    _write_cpuinfo(root, "model name\t: AMD Ryzen Z2 Extreme\n")
    assert read_cpu_model(root=root) == "AMD Ryzen Z2 Extreme"


def test_cpu_model_missing_is_none(tmp_path):
    assert read_cpu_model(root=str(tmp_path)) is None
