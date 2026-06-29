import os

from power.reader import PowerReader


def _mk_hwmon(root, idx, name, files):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(name)
    for k, v in files.items():
        with open(os.path.join(d, k), "w") as f:
            f.write(str(v))


def _mk_drm_card(root, idx, gpu_busy_percent):
    d = os.path.join(root, "sys/class/drm", f"card{idx}", "device")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "gpu_busy_percent"), "w") as f:
        f.write(str(gpu_busy_percent))


def test_reads_amdgpu_power_average(tmp_path):
    _mk_hwmon(str(tmp_path), 0, "BAT0", {"power1_input": 12498000})
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": 13055000, "power1_input": 13056000})
    assert PowerReader(root=str(tmp_path)).read_watts() == 13.1  # 13.055 -> 13.1


def test_falls_back_to_power_input(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_input": 9500000})
    assert PowerReader(root=str(tmp_path)).read_watts() == 9.5


def test_none_when_no_amdgpu(tmp_path):
    _mk_hwmon(str(tmp_path), 0, "k10temp", {"temp1_input": 50000})
    assert PowerReader(root=str(tmp_path)).read_watts() is None


def test_none_on_garbage(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": "x", "power1_input": "0"})
    assert PowerReader(root=str(tmp_path)).read_watts() is None


def test_read_dict_shape(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": 10000000})
    r = PowerReader(root=str(tmp_path)).read()
    assert r == {"watts": 10.0, "gpu_busy": None}


# --- gpu_busy tests ---

def test_reads_gpu_busy_percent(tmp_path):
    _mk_drm_card(str(tmp_path), 0, 72)
    assert PowerReader(root=str(tmp_path)).read_gpu_busy() == 72


def test_gpu_busy_none_when_absent(tmp_path):
    assert PowerReader(root=str(tmp_path)).read_gpu_busy() is None


def test_gpu_busy_clamps_to_100(tmp_path):
    _mk_drm_card(str(tmp_path), 0, 150)
    busy = PowerReader(root=str(tmp_path)).read_gpu_busy()
    assert busy == 100


def test_gpu_busy_clamps_to_0(tmp_path):
    _mk_drm_card(str(tmp_path), 0, -5)
    busy = PowerReader(root=str(tmp_path)).read_gpu_busy()
    assert busy == 0


def test_gpu_busy_none_on_corrupt(tmp_path):
    _mk_drm_card(str(tmp_path), 0, "bogus")
    assert PowerReader(root=str(tmp_path)).read_gpu_busy() is None


def test_gpu_busy_picks_first_sorted_card(tmp_path):
    _mk_drm_card(str(tmp_path), 0, 30)
    _mk_drm_card(str(tmp_path), 1, 80)
    assert PowerReader(root=str(tmp_path)).read_gpu_busy() == 30


def test_read_returns_both_fields(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": 15000000})
    _mk_drm_card(str(tmp_path), 0, 55)
    r = PowerReader(root=str(tmp_path)).read()
    assert r["watts"] == 15.0
    assert r["gpu_busy"] == 55
