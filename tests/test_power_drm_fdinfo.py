import os
import threading

from power import drm_fdinfo
from power.drm_fdinfo import DrmFdinfoGpuBusy


def _client(root, pid, fd, client, busy_ns, driver="msm"):
    path = root / "proc" / str(pid) / "fdinfo"
    path.mkdir(parents=True, exist_ok=True)
    links = root / "proc" / str(pid) / "fd"
    links.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(links / str(fd)):
        os.symlink("/dev/dri/renderD128", links / str(fd))
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
    now = {"t": 0.0}
    reader._fdinfo_gpu._clock = lambda: now["t"]
    assert reader.read_gpu_busy() is None
    assert reader.gpu_diagnostics() == {"source": "drm_fdinfo", "state": "warming_up"}
    _client(tmp_path, 100, 5, "7", 10_000_000_000)
    now["t"] = 2.0
    assert reader.read_gpu_busy() == 100
    assert reader.gpu_diagnostics()["state"] == "ok"


def test_reads_inside_one_second_reuse_the_last_window(tmp_path):
    now = {"t": 0.0}
    _client(tmp_path, 100, 5, "7", 0)
    reader = DrmFdinfoGpuBusy(root=str(tmp_path), clock=lambda: now["t"])
    reader.read()
    now["t"] = 1.0
    _client(tmp_path, 100, 5, "7", 500_000_000)
    assert reader.read() == 50
    now["t"] = 1.01
    _client(tmp_path, 100, 5, "7", 510_000_000)
    assert reader.read() == 50
    now["t"] = 2.0
    _client(tmp_path, 100, 5, "7", 600_000_000)
    assert reader.read() == 10


def test_new_gpu_clients_are_found_by_the_periodic_rescan(tmp_path):
    now = {"t": 0.0}
    _client(tmp_path, 100, 5, "7", 0)
    reader = DrmFdinfoGpuBusy(root=str(tmp_path), clock=lambda: now["t"])
    reader.read()
    _client(tmp_path, 400, 2, "11", 0)
    now["t"] = 1.0
    reader.read()
    assert len(reader._paths) == 1
    now["t"] = 1.0 + drm_fdinfo._RESCAN_S
    reader.read()
    assert len(reader._paths) == 2


def test_only_descriptors_on_a_drm_device_are_read(tmp_path):
    _client(tmp_path, 100, 5, "7", 0)
    other = tmp_path / "proc" / "100"
    (other / "fdinfo" / "6").write_text("pos:\t0\nflags:\t02\n")
    os.symlink("/home/user/save.dat", other / "fd" / "6")
    assert drm_fdinfo._gpu_fdinfo_paths(str(tmp_path)) == [str(other / "fdinfo" / "5")]


def test_a_scan_in_flight_is_not_started_twice(tmp_path, monkeypatch):
    _client(tmp_path, 100, 5, "7", 0)
    reader = DrmFdinfoGpuBusy(root=str(tmp_path))
    started, release = threading.Event(), threading.Event()
    scans = []

    def slow_scan(root, paths=None):
        scans.append(root)
        started.set()
        release.wait(2)
        return {}, []

    monkeypatch.setattr(drm_fdinfo, "_clients", slow_scan)
    first = threading.Thread(target=reader.read)
    first.start()
    started.wait(2)
    assert reader.read() is None
    release.set()
    first.join()
    assert len(scans) == 1


def test_missing_amdgpu_sources_are_not_searched_on_every_read(tmp_path, monkeypatch):
    from power import reader as power_reader

    now = {"t": 0.0}
    (tmp_path / "sys/class/devfreq/3d00000.gpu").mkdir(parents=True)
    reader = power_reader.PowerReader(root=str(tmp_path), gpu_samples=1, gpu_sample_gap=0, clock=lambda: now["t"])
    searches = []
    monkeypatch.setattr(reader, "_find_amdgpu_dir", lambda: searches.append("amdgpu"))
    monkeypatch.setattr(reader, "_find_gpu_busy_path", lambda: searches.append("busy"))
    for _ in range(50):
        reader.read()
    assert searches == []
    now["t"] = power_reader._REPROBE_S + 1
    reader.read()
    reader.read()
    assert sorted(searches) == ["amdgpu", "busy"]
