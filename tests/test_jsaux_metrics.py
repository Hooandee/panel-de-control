from accessories.jsaux_pixel import metrics


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _fake_sys(root, cpu_idle_a=800, cpu_total_a=1000, cpu_idle_b=850, cpu_total_b=1100):
    _write(root, "proc/stat", f"cpu  {cpu_total_a - cpu_idle_a} 0 0 {cpu_idle_a} 0 0 0 0 0 0\n")
    _write(root, "proc/meminfo", "MemTotal:       16000000 kB\nMemAvailable:    4000000 kB\n")
    hw = "sys/class/drm/card1/device"
    _write(root, f"{hw}/gpu_busy_percent", "37\n")
    _write(root, f"{hw}/hwmon/hwmon3/power1_average", "84500000\n")
    _write(root, f"{hw}/hwmon/hwmon3/temp1_input", "61000\n")
    _write(root, "sys/class/hwmon/hwmon1/name", "k10temp\n")
    _write(root, "sys/class/hwmon/hwmon1/temp1_input", "70500\n")
    return root


def test_reads_gpu_ram_watts_and_temperatures(tmp_path):
    reader = metrics.SystemMetrics(_fake_sys(tmp_path))
    sample = reader.sample()
    assert sample["gpu_pct"] == 37
    assert sample["ram_pct"] == 75
    assert sample["gpu_w"] == 84.5
    assert sample["gpu_temp"] == 61
    assert sample["cpu_temp"] == 70


def test_cpu_load_comes_from_the_delta_between_samples(tmp_path):
    clock = [0.0]
    reader = metrics.SystemMetrics(_fake_sys(tmp_path), clock=lambda: clock[0])
    assert reader.sample()["cpu_pct"] is None
    _write(tmp_path, "proc/stat", "cpu  250 0 0 850 0 0 0 0 0 0\n")
    clock[0] += 1
    assert reader.sample()["cpu_pct"] == 50


def test_missing_sensors_are_none_not_zero(tmp_path):
    sample = metrics.SystemMetrics(tmp_path).sample()
    assert all(value is None for value in sample.values())


def test_steps_hold_until_the_change_is_clear():
    step = metrics.Stepper(size=10, margin=3)
    assert step(41) == 40
    assert step(44) == 40
    assert step(47) == 40
    assert step(49) == 50
    assert step(46) == 50
    assert step(42) == 40
    assert step(None) is None


def test_back_to_back_samples_share_one_reading(tmp_path):
    clock = [100.0]
    reader = metrics.SystemMetrics(_fake_sys(tmp_path), clock=lambda: clock[0])
    reader.sample()
    _write(tmp_path, "proc/stat", "cpu  250 0 0 850 0 0 0 0 0 0\n")
    clock[0] += 0.2
    assert reader.sample()["cpu_pct"] is None
    clock[0] += 1.0
    assert reader.sample()["cpu_pct"] == 50
