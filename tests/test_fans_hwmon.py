import os

from fans.hwmon import FanReader, curate_fans, curate_temps, extract_cpu_gpu_temps


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


def test_ffff_rpm_glitch_is_reported_as_unknown_not_65535(tmp_path):
    # The Legion Go S lenovo_wmi_other driver briefly returns 0xFFFF (65535) while
    # the fan ramps — an all-ones sentinel, not a real speed. Keep the fan present
    # (it exists) but report rpm unknown for that read; never show 65535.
    root = str(tmp_path)
    _mk_chip(root, 0, "lenovo_wmi_other", {"fan1_input": "65535"})
    state = FanReader(root=root).read()
    assert state["supported"] is True
    assert len(state["fans"]) == 1
    assert state["fans"][0]["rpm"] is None


def test_uses_fan_label_when_present(tmp_path):
    root = str(tmp_path)
    _mk_chip(root, 0, "x", {"fan1_input": "1500", "fan1_label": "CPU Fan"})
    fan = FanReader(root=root).read()["fans"][0]
    assert fan["label"] == "CPU Fan"


def test_unlabeled_fan_gets_friendly_generic_label_not_raw_chip_name(tmp_path):
    # The lenovo_wmi_other chip exposes no fanN_label, so the fallback must be a
    # clean generic label ("Fan 1"), not the raw chip name ("lenovo_wmi_other 1").
    root = str(tmp_path)
    _mk_chip(root, 0, "lenovo_wmi_other", {"fan1_input": "9415"})
    fan = FanReader(root=root).read()["fans"][0]
    assert fan["label"] == "Fan 1"


def test_lenovo_wmi_other_drops_phantom_zero_channel(tmp_path):
    # Legion Go original (83E1): one physical fan, but lenovo_wmi_other over-exposes
    # a fixed 2-channel layout ("all fans exposed. Use with caution"). The 0-RPM
    # second channel is a phantom → keep only the real spinning fan.
    root = str(tmp_path)
    _mk_chip(root, 0, "lenovo_wmi_other", {"fan1_input": "9415", "fan2_input": "0"})
    fans = FanReader(root=root).read()["fans"]
    assert len(fans) == 1
    assert fans[0]["rpm"] == 9415


def test_lenovo_wmi_other_all_zero_keeps_single_fan(tmp_path):
    # Silent mode (both channels read 0) still collapses to the one physical fan.
    root = str(tmp_path)
    _mk_chip(root, 0, "lenovo_wmi_other", {"fan1_input": "0", "fan2_input": "0"})
    fans = FanReader(root=root).read()["fans"]
    assert len(fans) == 1


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


# --- extract_cpu_gpu_temps ---------------------------------------------------

def test_extract_with_cpu_gpu_labels():
    state = {
        "temps": [
            {"label": "CPU", "celsius": 58.2},
            {"label": "GPU", "celsius": 56.0},
            {"label": "Composite", "celsius": 33.0},
        ]
    }
    cpu, gpu = extract_cpu_gpu_temps(state)
    assert cpu == 58.2
    assert gpu == 56.0


def test_extract_falls_back_to_position():
    state = {
        "temps": [
            {"label": "Tctl", "celsius": 61.0},
            {"label": "edge", "celsius": 54.5},
        ]
    }
    cpu, gpu = extract_cpu_gpu_temps(state)
    assert cpu == 61.0
    assert gpu == 54.5


def test_extract_empty_returns_none_none():
    cpu, gpu = extract_cpu_gpu_temps({"temps": []})
    assert cpu is None
    assert gpu is None


# --- device-aware curation (refined from real Ally X hwmon layout) -----------

def test_temps_keep_only_cpu_gpu_and_drop_noise(tmp_path):
    root = str(tmp_path)
    # Enumeration order puts noise first; curation must surface CPU/GPU and DROP
    # the noisy sensors (nvme/acpitz/wifi) entirely — they clutter the monitor.
    _mk_chip(root, 4, "nvme", {"temp1_input": "33850", "temp1_label": "Composite"})
    _mk_chip(root, 5, "acpitz", {"temp1_input": "45000"})
    _mk_chip(root, 6, "mt7921", {"temp1_input": "40000"})
    _mk_chip(root, 7, "amdgpu", {"temp1_input": "56000", "temp1_label": "edge"})
    _mk_chip(root, 8, "k10temp", {"temp1_input": "58250", "temp1_label": "Tctl"})
    temps = FanReader(root=root).read()["temps"]
    assert [t["label"] for t in temps] == ["CPU", "GPU"]  # noise dropped
    assert temps[0]["celsius"] == 58.2


def test_temps_fallback_keeps_all_when_no_cpu_gpu(tmp_path):
    # A device exposing only unrecognized sensors must still show them (honest
    # fallback), not an empty list.
    root = str(tmp_path)
    _mk_chip(root, 0, "acpitz", {"temp1_input": "45000"})
    _mk_chip(root, 1, "nvme", {"temp1_input": "33850", "temp1_label": "Composite"})
    temps = FanReader(root=root).read()["temps"]
    assert len(temps) == 2


def test_curate_collapses_intel_multicore_to_single_cpu_max():
    # MSI Claw: coretemp exposes Package + per-core, all map to "CPU" → collapse to
    # one row showing the hottest, instead of a wall of duplicate "CPU" lines.
    temps = [
        {"chip": "coretemp", "label": "Core 0", "celsius": 46.0},
        {"chip": "coretemp", "label": "Core 1", "celsius": 50.0},
        {"chip": "coretemp", "label": "Package id 0", "celsius": 47.0},
    ]
    out = curate_temps(temps)
    assert len(out) == 1
    assert out[0]["label"] == "CPU"
    assert out[0]["celsius"] == 50.0  # hottest core


def test_curate_gpu_without_cpu_is_labelled_apu():
    # Steam Deck exposes only amdgpu (no k10temp) — the single APU die sensor.
    # Label it "APU", not "GPU" (which falsely implies a discrete graphics temp).
    out = curate_temps([{"chip": "amdgpu", "label": "edge", "celsius": 43.0}])
    assert len(out) == 1
    assert out[0]["label"] == "APU"


def _fan(label, rpm, chip="vendor"):
    return {"chip": chip, "label": label, "rpm": rpm, "percent": None}


def test_curate_fans_caps_at_two_preferring_spinning():
    # MSI Claw: msi_wmi_platform exposes 4 channels but only 2 physical fans spin;
    # the 2 phantom 0-RPM channels must be dropped → at most 2 chips shown.
    fans = [_fan("f1", 2474), _fan("f2", 2461), _fan("f3", 0), _fan("f4", 0)]
    out = curate_fans(fans)
    assert len(out) == 2
    assert [f["rpm"] for f in out] == [2474, 2461]


def test_curate_fans_all_zero_keeps_first_two():
    # Silent mode (every channel 0 RPM is real) → still cap at 2, keep the first two.
    fans = [_fan("f1", 0), _fan("f2", 0), _fan("f3", 0), _fan("f4", 0)]
    out = curate_fans(fans)
    assert len(out) == 2


def test_curate_fans_two_or_fewer_unchanged():
    fans = [_fan("cpu", 4400), _fan("gpu", 4500)]
    assert curate_fans(fans) == fans
    assert len(curate_fans([_fan("only", 528)])) == 1


def test_curate_fans_collapses_lenovo_wmi_other_phantom():
    # Legion Go original: lenovo_wmi_other exposes 2 channels but the device has one
    # physical fan; drop the phantom 0-RPM channel, keep the spinning one.
    fans = [_fan("Fan 1", 9415, chip="lenovo_wmi_other"),
            _fan("Fan 2", 0, chip="lenovo_wmi_other")]
    out = curate_fans(fans)
    assert len(out) == 1
    assert out[0]["rpm"] == 9415


def test_curate_fans_does_not_collapse_other_two_fan_chips():
    # A genuine two-fan chip (e.g. Ally's lock-step pair) is untouched, even with a
    # channel idling at 0 — only lenovo_wmi_other is known to over-expose a phantom.
    fans = [_fan("cpu", 4400), _fan("gpu", 0)]
    assert curate_fans(fans) == fans


def test_curate_keeps_cpu_and_gpu_distinct_when_both_present():
    # AMD Ally/Legion: k10temp + amdgpu → CPU + GPU, NOT collapsed to APU.
    out = curate_temps([
        {"chip": "k10temp", "label": "Tctl", "celsius": 57.5},
        {"chip": "amdgpu", "label": "edge", "celsius": 50.0},
    ])
    assert [t["label"] for t in out] == ["CPU", "GPU"]
