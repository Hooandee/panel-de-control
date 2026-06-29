import os

from fans.hwmon import FanReader


def _mk_chip(root, idx, name, files):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(name)
    for fname, val in files.items():
        with open(os.path.join(d, fname), "w") as f:
            f.write(val)
    return d


def test_no_hwmon_is_unsupported(tmp_path):
    state = FanReader(root=str(tmp_path)).read()
    assert state["supported"] is False
    assert state["fans"] == []
    assert state["temps"] == []


def test_reads_single_fan_rpm_and_pwm_percent(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "asus", {"fan1_input": "3200", "pwm1": "128"})
    state = FanReader(root=root).read()
    assert state["supported"] is True
    assert len(state["fans"]) == 1
    fan = state["fans"][0]
    assert fan["rpm"] == 3200
    assert fan["percent"] == 50  # 128/255 ~= 50%


def test_reads_two_fans(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "legion", {"fan1_input": "2000", "fan2_input": "2500"})
    fans = FanReader(root=root).read()["fans"]
    assert len(fans) == 2
    assert {f["rpm"] for f in fans} == {2000, 2500}


def test_fan_without_pwm_has_none_percent(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "x", {"fan1_input": "1500"})
    fan = FanReader(root=root).read()["fans"][0]
    assert fan["percent"] is None


def test_uses_fan_label_when_present(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "x", {"fan1_input": "1500", "fan1_label": "CPU Fan"})
    fan = FanReader(root=root).read()["fans"][0]
    assert fan["label"] == "CPU Fan"


def test_reads_temps_in_celsius(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "x", {"fan1_input": "1500", "temp1_input": "54800", "temp1_label": "CPU"})
    temps = FanReader(root=root).read()["temps"]
    assert {"label": "CPU", "celsius": 54.8} in temps


def test_corrupt_values_skipped(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "x", {"fan1_input": "garbage", "fan2_input": "1800"})
    fans = FanReader(root=root).read()["fans"]
    assert len(fans) == 1 and fans[0]["rpm"] == 1800


# --- device-aware curation (refined from real Ally X hwmon layout) -----------

def test_drops_generic_acpi_fan_when_a_vendor_fan_exists(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 1, "acpi_fan", {"fan1_input": "0"})
    _mk_chip(root, 9, "asus", {"fan1_input": "0", "fan1_label": "cpu_fan"})
    labels = [f["label"] for f in FanReader(root=root).read()["fans"]]
    assert labels == ["cpu_fan"]  # generic acpi_fan dropped


def test_keeps_acpi_fan_when_it_is_the_only_source(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 1, "acpi_fan", {"fan1_input": "1200"})
    assert len(FanReader(root=root).read()["fans"]) == 1


def test_temps_prioritize_cpu_and_gpu_and_relabel(tmp_path):
    root = str(tmp_path)
    # Enumeration order puts noise first; curation must surface CPU/GPU.
    _mk_chip(root, 4, "nvme", {"temp1_input": "33850", "temp1_label": "Composite"})
    _mk_chip(root, 7, "amdgpu", {"temp1_input": "56000", "temp1_label": "edge"})
    _mk_chip(root, 8, "k10temp", {"temp1_input": "58250", "temp1_label": "Tctl"})
    temps = FanReader(root=root).read()["temps"]
    assert [t["label"] for t in temps[:2]] == ["CPU", "GPU"]
    assert temps[0]["celsius"] == 58.2
