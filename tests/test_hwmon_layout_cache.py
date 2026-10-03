from fans import hwmon
from fans.hwmon import FanReader


def _chip(root, index, name, fans=(), temps=()):
    chip = root / "sys/class/hwmon" / f"hwmon{index}"
    chip.mkdir(parents=True, exist_ok=True)
    (chip / "name").write_text(name + "\n")
    for n, rpm in fans:
        (chip / f"fan{n}_input").write_text(f"{rpm}\n")
    for n, milli in temps:
        (chip / f"temp{n}_input").write_text(f"{milli}\n")
    return chip


def test_values_stay_live_while_the_layout_is_reused(tmp_path, monkeypatch):
    chip = _chip(tmp_path, 0, "armada_fan", fans=[(1, 2000)], temps=[(1, 50000)])
    reader = FanReader(root=str(tmp_path))
    scans = []
    original = reader._scan_layout
    monkeypatch.setattr(reader, "_scan_layout", lambda: scans.append(1) or original())
    assert reader.read()["fans"][0]["rpm"] == 2000
    (chip / "fan1_input").write_text("3100\n")
    assert reader.read()["fans"][0]["rpm"] == 3100
    assert len(scans) == 1


def test_a_vanished_chip_or_a_loaded_driver_refreshes_the_layout(tmp_path):
    chip = _chip(tmp_path, 0, "armada_fan", fans=[(1, 2000)])
    reader = FanReader(root=str(tmp_path))
    assert len(reader.read()["fans"]) == 1
    (chip / "fan1_input").unlink()
    reader.read()
    _chip(tmp_path, 1, "it87", fans=[(1, 900)])
    assert len(reader.read()["fans"]) == 1
    reader.invalidate()
    _chip(tmp_path, 2, "nct6775", fans=[(1, 700)])
    assert len(reader.read()["fans"]) == 2
    assert hwmon._LAYOUT_TTL_S >= 30


def _equivalent(reader):
    from fans.hwmon import extract_cpu_gpu_temps

    return reader.driving_temps() == extract_cpu_gpu_temps(reader.read())


def test_driving_temps_match_the_full_read_on_a_snapdragon(tmp_path):
    _chip(tmp_path, 0, "cpu7_middle_thermal", temps=[(1, 61200)])
    _chip(tmp_path, 1, "cpuss0_thermal", temps=[(1, 58300)])
    _chip(tmp_path, 2, "gpuss_0_thermal", temps=[(1, 55100)])
    _chip(tmp_path, 3, "modem2_thermal", temps=[(1, 70000)])
    _chip(tmp_path, 4, "pwmfan", fans=[(1, 3000)])
    reader = FanReader(root=str(tmp_path))
    assert reader.driving_temps() == (61.2, 55.1)
    assert _equivalent(reader)


def test_driving_temps_match_the_full_read_on_an_amd_handheld(tmp_path):
    _chip(tmp_path, 0, "k10temp", temps=[(1, 72500)])
    _chip(tmp_path, 1, "amdgpu", temps=[(1, 64000)])
    _chip(tmp_path, 2, "nvme", temps=[(1, 45000)])
    reader = FanReader(root=str(tmp_path))
    assert reader.driving_temps() == (72.5, 64.0)
    assert _equivalent(reader)


def test_machines_without_known_sensors_fall_back_to_the_full_read(tmp_path):
    _chip(tmp_path, 0, "acpitz", temps=[(1, 50000)])
    assert FanReader(root=str(tmp_path)).driving_temps() is None
