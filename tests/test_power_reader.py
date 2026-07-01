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


# --- gpu_busy sub-sampling (Van Gogh instantaneous-sensor de-noise) ---

def _reader_with_samples(tmp_path, samples):
    """A PowerReader whose gpu_busy path resolves, but whose per-read value is
    driven by a scripted sequence (simulating the noisy instantaneous sensor).
    Sleeps are disabled so tests run instantly."""
    _mk_drm_card(str(tmp_path), 0, 0)  # make _find_gpu_busy_path succeed
    r = PowerReader(root=str(tmp_path), gpu_samples=len(samples), gpu_sample_gap=0.0)
    seq = list(samples)

    def fake_read_int(_path):
        return seq.pop(0) if seq else None

    r._read_int = fake_read_int
    return r


def test_gpu_busy_averages_a_burst(tmp_path):
    # The exact on-device Van Gogh probe: instantaneous 0<->100 noise, ~22% real.
    samples = [0, 0, 0, 100, 100, 100, 0, 0, 0, 0, 53, 59, 0, 0, 0, 37, 0, 0, 0, 0]
    r = _reader_with_samples(tmp_path, samples)
    # mean = 449/20 = 22.45 -> 22 (a single instantaneous read would give a bogus 0,
    # matching gamescope's smoothed ~30% and the 5.2 W real draw)
    assert r.read_gpu_busy() == 22


def test_gpu_busy_burst_of_constant_is_that_value(tmp_path):
    r = _reader_with_samples(tmp_path, [72] * 12)
    assert r.read_gpu_busy() == 72


def test_gpu_busy_averages_only_valid_reads(tmp_path):
    # Corrupt reads (None) are ignored; the mean is over the valid ones only.
    r = _reader_with_samples(tmp_path, [None, 80, None, 40, None])
    assert r.read_gpu_busy() == 60  # mean(80, 40)


def test_gpu_busy_none_when_no_valid_reads(tmp_path):
    # File vanished mid-burst / all corrupt -> honest None, never a fake 0.
    r = _reader_with_samples(tmp_path, [None, None, None])
    assert r.read_gpu_busy() is None


def test_gpu_busy_burst_clamps_per_read(tmp_path):
    r = _reader_with_samples(tmp_path, [150, 100, -5])
    # each read clamped to [0,100] -> mean(100, 100, 0) = 66.67 -> 67
    assert r.read_gpu_busy() == 67
