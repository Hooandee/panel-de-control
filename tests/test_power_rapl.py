import os

from power.rapl import RaplPackagePower


def _domain(root, name="package-0", energy=0, wrap=262143328850, index="0"):
    path = os.path.join(root, "sys/class/powercap", f"intel-rapl:{index}")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "name"), "w") as handle:
        handle.write(name + "\n")
    with open(os.path.join(path, "max_energy_range_uj"), "w") as handle:
        handle.write(str(wrap))
    _energy(path, energy)
    return path


def _energy(path, value):
    with open(os.path.join(path, "energy_uj"), "w") as handle:
        handle.write(str(value))


def test_package_power_is_the_energy_delta_over_time(tmp_path):
    path = _domain(str(tmp_path), energy=1_000_000)
    clock = {"now": 10.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])

    assert reader.read() is None
    _energy(path, 25_000_000)
    clock["now"] = 12.0

    assert reader.read() == 12.0


def test_counter_wrap_uses_the_reported_range(tmp_path):
    path = _domain(str(tmp_path), energy=990, wrap=1000)
    clock = {"now": 0.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])
    reader.read()
    _energy(path, 2_000_000 - 10)
    clock["now"] = 1.0

    assert reader.read() == 2.0


def test_missing_or_unreadable_rapl_is_unknown(tmp_path):
    assert RaplPackagePower(root=str(tmp_path)).read() is None
    _domain(str(tmp_path), name="psys")
    assert RaplPackagePower(root=str(tmp_path)).read() is None


def test_subdomains_are_not_mistaken_for_the_package(tmp_path):
    _domain(str(tmp_path), name="core", index="0:0")
    package = _domain(str(tmp_path), energy=0, index="1")
    clock = {"now": 0.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])
    reader.read()
    _energy(package, 5_000_000)
    clock["now"] = 1.0

    assert reader.read() == 5.0


def test_a_read_too_soon_repeats_the_last_result(tmp_path):
    path = _domain(str(tmp_path), energy=0)
    clock = {"now": 0.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])
    reader.read()
    _energy(path, 1_000_000)
    clock["now"] = 0.1
    assert reader.read() is None

    clock["now"] = 1.0
    assert reader.read() == 1.0
    _energy(path, 9_000_000)
    clock["now"] = 1.2
    assert reader.read() == 1.0


def test_a_machine_without_rapl_is_not_rescanned_every_read(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])
    scans = []
    monkeypatch.setattr(reader, "_find_domain", lambda: scans.append(True))

    for _ in range(5):
        reader.read()
    clock["now"] = RaplPackagePower._REPROBE_S + 1
    reader.read()

    assert len(scans) == 2


def test_a_stale_sample_is_not_averaged_over_a_long_pause(tmp_path):
    path = _domain(str(tmp_path), energy=0)
    clock = {"now": 0.0}
    reader = RaplPackagePower(root=str(tmp_path), clock=lambda: clock["now"])
    reader.read()
    _energy(path, 3_600_000_000)
    clock["now"] = 3600.0

    assert reader.read() is None
    _energy(path, 3_610_000_000)
    clock["now"] = 3602.0
    assert reader.read() == 5.0
