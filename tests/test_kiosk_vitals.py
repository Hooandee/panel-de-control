from kiosk import vitals


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_thor_like_tree(tmp_path):
    for policy, khz in (("policy0", 1459200), ("policy3", 2054400), ("policy7", 2092800)):
        _write(tmp_path, f"sys/devices/system/cpu/cpufreq/{policy}/scaling_cur_freq", f"{khz}\n")
    _write(tmp_path, "sys/class/devfreq/1d84000.ufshc/cur_freq", "75000000\n")
    _write(tmp_path, "sys/class/devfreq/3d00000.gpu/cur_freq", "220000000\n")
    _write(tmp_path, "proc/meminfo", "MemTotal:       11758392 kB\nMemFree: 1 kB\nMemAvailable:    6102296 kB\n")
    assert vitals.read(str(tmp_path)) == {
        "cpu_mhz": 2093,
        "gpu_mhz": 220,
        "ram_used_gb": 5.39,
        "ram_total_gb": 11.2,
    }


def test_storage_devfreq_is_not_a_gpu_and_amdgpu_hwmon_is(tmp_path):
    _write(tmp_path, "sys/class/devfreq/1d84000.ufshc/cur_freq", "75000000\n")
    assert vitals.gpu_mhz(str(tmp_path)) is None
    _write(tmp_path, "sys/class/drm/card1/device/hwmon/hwmon3/freq1_input", "1600000000\n")
    assert vitals.gpu_mhz(str(tmp_path)) == 1600


def test_missing_sources_stay_unknown(tmp_path):
    assert vitals.read(str(tmp_path)) == {
        "cpu_mhz": None,
        "gpu_mhz": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
    }
