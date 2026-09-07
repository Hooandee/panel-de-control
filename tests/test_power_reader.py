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


def _mk_correlated_gpu(
    root, *, hwmon_idx, card_idx, pci_id, hwmon_files, gpu_busy_percent,
    vram_used_gib, vram_total_gib,
):
    device = os.path.join(root, "sys/devices/pci0000:00", pci_id)
    os.makedirs(device, exist_ok=True)
    with open(os.path.join(device, "gpu_busy_percent"), "w") as handle:
        handle.write(str(gpu_busy_percent))
    with open(os.path.join(device, "mem_info_vram_used"), "w") as handle:
        handle.write(str(vram_used_gib * 1024 * 1024 * 1024))
    with open(os.path.join(device, "mem_info_vram_total"), "w") as handle:
        handle.write(str(vram_total_gib * 1024 * 1024 * 1024))

    hwmon = os.path.join(root, "sys/class/hwmon", f"hwmon{hwmon_idx}")
    os.makedirs(hwmon, exist_ok=True)
    with open(os.path.join(hwmon, "name"), "w") as handle:
        handle.write("amdgpu")
    for leaf, value in hwmon_files.items():
        with open(os.path.join(hwmon, leaf), "w") as handle:
            handle.write(str(value))
    os.symlink(device, os.path.join(hwmon, "device"))

    card = os.path.join(root, "sys/class/drm", f"card{card_idx}")
    os.makedirs(card, exist_ok=True)
    os.symlink(device, os.path.join(card, "device"))


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


def test_desktop_snapshot_names_gpu_domain_and_reads_clock_and_vram(tmp_path):
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=7,
        card_idx=0,
        pci_id="0000:03:00.0",
        hwmon_files={
            "power1_average": 18_400_000,
            "freq1_input": 1_850_000_000,
            "freq1_max": 2_209_000_000,
        },
        gpu_busy_percent=61,
        vram_used_gib=3,
        vram_total_gib=8,
    )
    snapshot = PowerReader(root=str(tmp_path), gpu_samples=1).read_desktop()
    assert snapshot == {
        "cpu_watts": None,
        "gpu_watts": 18.4,
        "gpu_busy": 61,
        "gpu_clock_mhz": 1850,
        "gpu_clock_max_mhz": 2209,
        "vram_used_mb": 3072,
        "vram_total_mb": 8192,
    }


def test_generic_desktop_hides_uncorrelated_gpu_metrics(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": 13_000_000})
    _mk_drm_card(str(tmp_path), 0, 74)

    snapshot = PowerReader(root=str(tmp_path), gpu_samples=1).read_desktop(
        device_key="generic"
    )

    assert snapshot == {
        "cpu_watts": None,
        "gpu_watts": None,
        "gpu_busy": None,
        "gpu_clock_mhz": None,
        "gpu_clock_max_mhz": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
    }


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


def test_gpu_busy_keeps_legacy_first_card_for_non_desktop_consumers(tmp_path):
    _mk_drm_card(str(tmp_path), 0, 30)
    _mk_drm_card(str(tmp_path), 1, 80)
    assert PowerReader(root=str(tmp_path)).read_gpu_busy() == 30


def test_only_fremont_snapshot_fails_closed_for_uncorrelated_devices(tmp_path):
    _mk_hwmon(str(tmp_path), 7, "amdgpu", {"power1_average": 15_000_000})
    _mk_drm_card(str(tmp_path), 0, 55)
    reader = PowerReader(root=str(tmp_path), gpu_samples=1)

    assert reader.read() == {"watts": 15.0, "gpu_busy": 55}
    assert reader.read_desktop(device_key="steam_machine") == {
        "cpu_watts": None,
        "gpu_watts": None,
        "gpu_busy": None,
        "gpu_clock_mhz": None,
        "gpu_clock_max_mhz": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
    }


def test_desktop_snapshot_uses_one_correlated_gpu_when_sysfs_order_differs(tmp_path):
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=2,
        card_idx=1,
        pci_id="0000:09:00.0",
        hwmon_files={
            "power1_average": 90_000_000,
            "freq1_input": 900_000_000,
            "freq1_max": 1_500_000_000,
        },
        gpu_busy_percent=99,
        vram_used_gib=12,
        vram_total_gib=16,
    )
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=9,
        card_idx=0,
        pci_id="0000:03:00.0",
        hwmon_files={
            "power1_average": 18_400_000,
            "freq1_input": 1_850_000_000,
            "freq1_max": 2_209_000_000,
            "power1_cap": 80_000_000,
            "power1_cap_min": 55_000_000,
            "power1_cap_max": 110_000_000,
        },
        gpu_busy_percent=61,
        vram_used_gib=3,
        vram_total_gib=8,
    )

    snapshot = PowerReader(root=str(tmp_path), gpu_samples=1).read_desktop(
        device_key="steam_machine"
    )

    assert snapshot == {
        "cpu_watts": None,
        "gpu_watts": 18.4,
        "gpu_busy": 61,
        "gpu_clock_mhz": 1850,
        "gpu_clock_max_mhz": 2209,
        "vram_used_mb": 3072,
        "vram_total_mb": 8192,
    }


def test_desktop_snapshot_hides_all_gpu_metrics_when_power_target_is_ambiguous(
    tmp_path,
):
    cap_files = {
        "power1_cap": 80_000_000,
        "power1_cap_min": 55_000_000,
        "power1_cap_max": 110_000_000,
    }
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=2,
        card_idx=1,
        pci_id="0000:09:00.0",
        hwmon_files={**cap_files, "power1_average": 90_000_000},
        gpu_busy_percent=99,
        vram_used_gib=12,
        vram_total_gib=16,
    )
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=9,
        card_idx=0,
        pci_id="0000:03:00.0",
        hwmon_files={**cap_files, "power1_average": 18_400_000},
        gpu_busy_percent=61,
        vram_used_gib=3,
        vram_total_gib=8,
    )

    snapshot = PowerReader(root=str(tmp_path), gpu_samples=1).read_desktop(
        device_key="steam_machine"
    )

    assert snapshot == {
        "cpu_watts": None,
        "gpu_watts": None,
        "gpu_busy": None,
        "gpu_clock_mhz": None,
        "gpu_clock_max_mhz": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
    }


def test_read_returns_both_fields(tmp_path):
    _mk_correlated_gpu(
        str(tmp_path),
        hwmon_idx=7,
        card_idx=0,
        pci_id="0000:03:00.0",
        hwmon_files={"power1_average": 15_000_000},
        gpu_busy_percent=55,
        vram_used_gib=0,
        vram_total_gib=8,
    )
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
    # Van Gogh-style probe: instantaneous 0<->100 noise, ~22% real.
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
