import os

from auto_tdp import AutoTdpController
from power.intel import IntelGpuUtil
from power.reader import PowerReader


def _write_fdinfo(
    root,
    pid,
    fd,
    client_id,
    busy,
    total,
    *,
    engine="rcs",
    driver="xe",
):
    directory = os.path.join(root, "proc", str(pid), "fdinfo")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, str(fd)), "w") as handle:
        handle.write(
            f"drm-driver:\t{driver}\n"
            "drm-pdev:\t0000:00:02.0\n"
            f"drm-client-id:\t{client_id}\n"
            f"drm-cycles-{engine}:\t{busy}\n"
            f"drm-total-cycles-{engine}:\t{total}\n"
        )


def test_power_reader_uses_successive_xe_fdinfo_samples(tmp_path):
    root = str(tmp_path)
    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    reader = PowerReader(root=root)
    reader._intel_gpu._cache_s = 0

    assert reader.read_gpu_busy() is None
    _write_fdinfo(root, 100, 3, 7, 600, 2_000)

    assert reader.read_gpu_busy() == 50
    diagnostics = reader.gpu_diagnostics()
    assert diagnostics["source"] == "intel_xe_fdinfo"
    assert diagnostics["state"] == "ok"
    assert diagnostics["clients"] == 1
    assert diagnostics["engines"] == 1


def test_xe_duplicate_file_descriptors_count_one_drm_client(tmp_path):
    root = str(tmp_path)
    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    _write_fdinfo(root, 100, 4, 7, 100, 1_000)
    reader = PowerReader(root=root)
    reader._intel_gpu._cache_s = 0
    assert reader.read_gpu_busy() is None

    _write_fdinfo(root, 100, 3, 7, 600, 2_000)
    _write_fdinfo(root, 100, 4, 7, 600, 2_000)

    assert reader.read_gpu_busy() == 50


def test_xe_client_appearing_after_initial_probe_is_retried(tmp_path):
    root = str(tmp_path)
    reader = PowerReader(root=root)
    reader._intel_gpu._cache_s = 0
    assert reader.read_gpu_busy() is None

    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    assert reader.read_gpu_busy() is None
    _write_fdinfo(root, 100, 3, 7, 700, 2_000)

    assert reader.read_gpu_busy() == 60


def test_xe_compute_engine_is_a_valid_gameplay_signal(tmp_path):
    root = str(tmp_path)
    _write_fdinfo(root, 100, 3, 7, 100, 1_000, engine="ccs")
    reader = PowerReader(root=root)
    reader._intel_gpu._cache_s = 0
    assert reader.read_gpu_busy() is None

    _write_fdinfo(root, 100, 3, 7, 900, 2_000, engine="ccs")

    assert reader.read_gpu_busy() == 80


def test_non_xe_fdinfo_is_not_reported_as_gpu_activity(tmp_path):
    root = str(tmp_path)
    _write_fdinfo(root, 100, 3, 7, 100, 1_000, driver="amdgpu")
    reader = PowerReader(root=root)
    assert reader.read_gpu_busy() is None


def test_existing_amdgpu_node_never_switches_to_an_intel_gpu(tmp_path):
    root = str(tmp_path)
    busy_path = os.path.join(
        root,
        "sys/class/drm/card0/device/gpu_busy_percent",
    )
    os.makedirs(os.path.dirname(busy_path), exist_ok=True)
    with open(busy_path, "w") as handle:
        handle.write("unreadable")
    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    reader = PowerReader(root=root)

    assert reader.read_gpu_busy() is None
    _write_fdinfo(root, 100, 3, 7, 900, 2_000)

    assert reader.read_gpu_busy() is None

    _write_fdinfo(root, 100, 3, 7, 900, 2_000, driver="amdgpu")

    assert reader.read_gpu_busy() is None


def test_detected_amdgpu_power_never_uses_an_unrelated_intel_gpu(tmp_path):
    root = str(tmp_path)
    hwmon = os.path.join(root, "sys/class/hwmon/hwmon0")
    os.makedirs(hwmon, exist_ok=True)
    with open(os.path.join(hwmon, "name"), "w") as handle:
        handle.write("amdgpu")
    with open(os.path.join(hwmon, "power1_average"), "w") as handle:
        handle.write("15000000")
    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    reader = PowerReader(root=root)

    assert reader.read() == {"watts": 15.0, "gpu_busy": None}
    assert reader.gpu_diagnostics() == {
        "source": "amdgpu",
        "state": "busy_unavailable",
    }
    _write_fdinfo(root, 100, 3, 7, 700, 2_000)

    assert reader.read() == {"watts": 15.0, "gpu_busy": None}


def test_xe_none_result_is_cached_after_the_scan_completes(tmp_path, monkeypatch):
    now = 0.0
    reader = IntelGpuUtil(root=str(tmp_path), cache_s=0.1)
    scans = 0

    def monotonic():
        return now

    def slow_empty_snapshot():
        nonlocal now, scans
        scans += 1
        now += 0.2
        return {}

    monkeypatch.setattr("power.intel.time.monotonic", monotonic)
    monkeypatch.setattr(reader, "_snapshot", slow_empty_snapshot)

    assert reader.read_gpu_busy() is None
    assert reader.read_gpu_busy() is None
    assert scans == 1


def test_xe_signal_lets_auto_tdp_leave_qualification_and_probe_down(tmp_path):
    root = str(tmp_path)
    _write_fdinfo(root, 100, 3, 7, 100, 1_000)
    reader = PowerReader(root=root)
    reader._intel_gpu._cache_s = 0
    now = 0.0
    controller = AutoTdpController(
        initial_w=17,
        min_w=8,
        max_w=30,
        target_fps=60,
        clock=lambda: now,
        warmup_s=0,
        stable_s=1,
        qualification_s=0,
        low_load_qualification_s=0,
    )

    waiting = controller.step(
        fps=60,
        signal_reason="ok",
        gpu_busy=reader.read_gpu_busy(),
    )
    _write_fdinfo(root, 100, 3, 7, 600, 2_000)
    qualifying = controller.step(
        fps=60,
        signal_reason="ok",
        gpu_busy=reader.read_gpu_busy(),
    )
    now = 1.0
    _write_fdinfo(root, 100, 3, 7, 1_100, 3_000)
    probe = controller.step(
        fps=60,
        signal_reason="ok",
        gpu_busy=reader.read_gpu_busy(),
    )

    assert waiting.reason == "awaiting_gameplay"
    assert qualifying.reason == "building_stability"
    assert (probe.setpoint, probe.reason) == (16, "probe_down")
