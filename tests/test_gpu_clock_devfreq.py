import os
from types import SimpleNamespace

from gpu.clock import DevfreqGpuClock, select_gpu_clock

TABLE = "220000000 295000000 348000000 401000000 475000000 550000000 615000000 680000000"


def _write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))
    return path


def _adreno(root, governor="simple_ondemand", minimum=220000000, maximum=680000000):
    base = "sys/class/devfreq/3d00000.gpu"
    _write(root, f"{base}/available_frequencies", TABLE + "\n")
    _write(root, f"{base}/min_freq", minimum)
    _write(root, f"{base}/max_freq", maximum)
    _write(root, f"{base}/governor", governor)
    _write(root, "sys/class/devfreq/1d84000.ufshc/available_frequencies", "75000000 300000000")
    _write(root, "sys/class/devfreq/1d84000.ufshc/min_freq", 75000000)
    _write(root, "sys/class/devfreq/1d84000.ufshc/max_freq", 300000000)
    return base


def _read(root, rel):
    with open(os.path.join(root, rel)) as handle:
        return handle.read().strip()


def test_adreno_devfreq_reports_its_table_range_in_mhz(tmp_path):
    root = str(tmp_path)
    _adreno(root)
    clock = DevfreqGpuClock(root)
    assert clock.supported is True
    assert clock.backend == "devfreq"
    assert clock.get_range() == (220, 680)
    assert clock.get() == (220, 680)


def test_manual_window_snaps_to_table_and_reads_back(tmp_path):
    root = str(tmp_path)
    base = _adreno(root)
    clock = DevfreqGpuClock(root)
    assert clock.set(300, 500) is True
    assert _read(root, f"{base}/min_freq") == "348000000"
    assert _read(root, f"{base}/max_freq") == "475000000"
    assert clock.get() == (348, 475)


def test_auto_restores_full_table_and_ondemand_governor(tmp_path):
    root = str(tmp_path)
    base = _adreno(root, governor="userspace", minimum=475000000, maximum=475000000)
    clock = DevfreqGpuClock(root)
    assert clock.set_auto() is True
    assert clock.get() == (220, 680)
    assert _read(root, f"{base}/governor") == "simple_ondemand"


def test_capture_and_restore_keep_governor_and_window(tmp_path):
    root = str(tmp_path)
    base = _adreno(root, governor="userspace", minimum=475000000, maximum=475000000)
    clock = DevfreqGpuClock(root)
    state = clock.capture_state()
    clock.set_auto()
    assert clock.restore_state(state) is True
    assert _read(root, f"{base}/governor") == "userspace"
    assert clock.get() == (475, 475)


def test_storage_devfreq_is_never_taken_for_the_gpu(tmp_path):
    root = str(tmp_path)
    _write(root, "sys/class/devfreq/1d84000.ufshc/available_frequencies", "75000000 300000000")
    _write(root, "sys/class/devfreq/1d84000.ufshc/min_freq", 75000000)
    _write(root, "sys/class/devfreq/1d84000.ufshc/max_freq", 300000000)
    assert DevfreqGpuClock(root).supported is False


def test_arm_selects_devfreq_and_x86_never_does(tmp_path):
    root = str(tmp_path)
    _adreno(root)
    arm = SimpleNamespace(arch="arm", vendor="qualcomm")
    x86 = SimpleNamespace(arch="x86", vendor="amd")
    assert select_gpu_clock(arm, root=root).backend == "devfreq"
    assert select_gpu_clock(x86, root=root).backend != "devfreq"


def test_levels_are_the_real_table_in_mhz(tmp_path):
    root = str(tmp_path)
    _adreno(root)
    assert DevfreqGpuClock(root).levels() == [220, 295, 348, 401, 475, 550, 615, 680]
