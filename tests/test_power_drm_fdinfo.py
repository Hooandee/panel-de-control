from power.drm_fdinfo import DrmFdinfoGpuBusy


def _client(root, pid, fd, client, busy_ns, driver="msm"):
    path = root / "proc" / str(pid) / "fdinfo"
    path.mkdir(parents=True, exist_ok=True)
    (path / str(fd)).write_text(
        f"pos:\t0\ndrm-driver:\t{driver}\ndrm-client-id:\t{client}\n"
        f"drm-engine-gpu:\t{busy_ns} ns\ndrm-cycles-gpu:\t0\n"
    )


def test_busy_share_is_measured_between_calls(tmp_path):
    now = {"t": 0.0}
    _client(tmp_path, 100, 5, "7", 0)
    _client(tmp_path, 200, 9, "8", 1_000_000_000)
    reader = DrmFdinfoGpuBusy(root=str(tmp_path), clock=lambda: now["t"])
    assert reader.read() is None
    now["t"] = 2.0
    _client(tmp_path, 100, 5, "7", 500_000_000)
    _client(tmp_path, 200, 9, "8", 1_300_000_000)
    assert reader.read() == 40


def test_duplicate_fds_of_one_client_count_once_and_closed_clients_never_go_negative(tmp_path):
    now = {"t": 0.0}
    _client(tmp_path, 100, 5, "7", 100)
    _client(tmp_path, 100, 6, "7", 100)
    _client(tmp_path, 300, 3, "9", 5_000_000_000)
    reader = DrmFdinfoGpuBusy(root=str(tmp_path), clock=lambda: now["t"])
    reader.read()
    now["t"] = 1.0
    _client(tmp_path, 100, 5, "7", 250_000_100)
    _client(tmp_path, 100, 6, "7", 250_000_100)
    (tmp_path / "proc" / "300" / "fdinfo" / "3").unlink()
    assert reader.read() == 25


def test_x86_drivers_are_ignored(tmp_path):
    now = {"t": 0.0}
    _client(tmp_path, 100, 5, "1", 0, driver="amdgpu")
    reader = DrmFdinfoGpuBusy(root=str(tmp_path), clock=lambda: now["t"])
    reader.read()
    now["t"] = 1.0
    _client(tmp_path, 100, 5, "1", 900_000_000, driver="amdgpu")
    assert reader.read() is None


def test_power_reader_uses_fdinfo_on_devfreq_gpus(tmp_path):
    from power.reader import PowerReader

    (tmp_path / "sys/class/devfreq/3d00000.gpu").mkdir(parents=True)
    _client(tmp_path, 100, 5, "7", 0)
    reader = PowerReader(root=str(tmp_path), gpu_samples=1, gpu_sample_gap=0)
    assert reader.read_gpu_busy() is None
    assert reader.gpu_diagnostics() == {"source": "drm_fdinfo", "state": "warming_up"}
    _client(tmp_path, 100, 5, "7", 10_000_000_000)
    assert reader.read_gpu_busy() == 100
    assert reader.gpu_diagnostics()["state"] == "ok"
