from battery.reader import BatteryReader


def _battery(tmp_path, **values):
    d = tmp_path / "sys/class/power_supply/battery"
    d.mkdir(parents=True)
    (d / "type").write_text("Battery\n")
    (d / "present").write_text("1\n")
    defaults = {"status": "Discharging", "capacity": "79", "charge_now": "4732236",
                "charge_full": "5963000", "charge_full_design": "5938000", "voltage_now": "4036236"}
    defaults.update(values)
    for name, value in defaults.items():
        (d / name).write_text(f"{value}\n")
    return str(tmp_path)


def test_thor_power_now_off_by_an_order_of_magnitude_uses_voltage_times_current(tmp_path):
    root = _battery(tmp_path, power_now="31489739", current_now="-659928")
    state = BatteryReader(root=root).read()
    assert state["power_now_w"] == 2.7
    assert 6.5 * 3600 < state["eta_seconds"] < 7.5 * 3600


def test_consistent_power_now_is_kept(tmp_path):
    root = _battery(tmp_path, power_now="2800000", current_now="-659928")
    assert BatteryReader(root=root).read()["power_now_w"] == 2.8
