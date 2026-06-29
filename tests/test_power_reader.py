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
    assert PowerReader(root=str(tmp_path)).read() == {"watts": 10.0}
