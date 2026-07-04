import os

from battery.reader import BatteryReader


def _mk_supply(root, name, files):
    d = os.path.join(root, "sys/class/power_supply", name)
    os.makedirs(d, exist_ok=True)
    for fname, val in files.items():
        with open(os.path.join(d, fname), "w") as f:
            f.write(str(val))
    return d


def test_no_battery_is_empty_but_honest(tmp_path):
    state = BatteryReader(root=str(tmp_path)).read()
    assert state["present"] is False
    assert state["percent"] is None


def test_reads_full_energy_battery(tmp_path):
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {
        "type": "Battery",
        "capacity": "73",
        "status": "Discharging",
        "energy_now": "30000000",       # µWh -> 30000 mWh
        "energy_full": "48000000",       # 48000 mWh
        "energy_full_design": "50000000",  # 50000 mWh
        "power_now": "15000000",         # µW -> 15 W
        "cycle_count": "142",
    })

    state = BatteryReader(root=root).read()
    assert state["present"] is True
    assert state["percent"] == 73
    assert state["status"] == "Discharging"
    assert state["energy_now_mwh"] == 30000
    assert state["energy_full_mwh"] == 48000
    assert state["energy_full_design_mwh"] == 50000
    assert state["health_percent"] == 96  # 48000/50000
    assert state["cycle_count"] == 142
    assert state["power_now_w"] == 15.0
    # eta = remaining(30000 mWh) / 15 W = 2h -> 7200 s
    assert state["eta_seconds"] == 7200


def test_charge_units_converted_via_voltage(tmp_path):
    # Devices exposing charge_* (µAh) + voltage_now (µV) instead of energy_*.
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {
        "type": "Battery",
        "capacity": "50",
        "status": "Charging",
        "charge_now": "3000000",        # 3 Ah
        "charge_full": "6000000",        # 6 Ah
        "voltage_now": "8000000",        # 8 V
    })
    state = BatteryReader(root=root).read()
    # energy = Ah * V: 3 * 8 = 24 Wh = 24000 mWh
    assert state["energy_now_mwh"] == 24000
    assert state["energy_full_mwh"] == 48000
    # no design -> hidden, no health
    assert state["energy_full_design_mwh"] is None
    assert state["health_percent"] is None


def test_power_falls_back_to_current_times_voltage(tmp_path):
    # Steam Deck exposes current_now (µA) + voltage_now (µV) but no power_now.
    root = str(tmp_path)
    _mk_supply(root, "BAT1", {
        "type": "Battery",
        "capacity": "58",
        "status": "Discharging",
        "charge_now": "3879000",
        "current_now": "3900000",    # 3.9 A
        "voltage_now": "8454000",    # 8.454 V
    })
    state = BatteryReader(root=root).read()
    # 3.9 A × 8.454 V ≈ 32.97 W
    assert state["power_now_w"] == 33.0


def test_health_caps_at_100_when_full_exceeds_design(tmp_path):
    # Fresh battery: charge_full > charge_full_design → health would be >100%.
    root = str(tmp_path)
    _mk_supply(root, "BAT1", {
        "type": "Battery",
        "capacity": "58",
        "status": "Charging",
        "charge_full": "6746000",
        "charge_full_design": "6470000",
        "voltage_min_design": "7760000",
    })
    state = BatteryReader(root=root).read()
    assert state["health_percent"] == 100


def test_missing_optional_fields_are_hidden(tmp_path):
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {"type": "Battery", "capacity": "88", "status": "Full"})
    state = BatteryReader(root=root).read()
    assert state["present"] is True
    assert state["percent"] == 88
    assert state["cycle_count"] is None
    assert state["health_percent"] is None
    assert state["eta_seconds"] is None


def test_zero_cycle_count_is_unknown(tmp_path):
    # Many handhelds (ASUS Ally, Steam Deck, MSI Claw) expose a cycle_count node
    # that the firmware never populates → it reads a literal "0". A used battery
    # with genuinely 0 cycles is implausible; showing "0 cycles" is a fake reading.
    # Treat 0 as unknown (None) so the UI hides the chip. Real counts
    # (Legion reports e.g. 38) are untouched.
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {"type": "Battery", "capacity": "60", "cycle_count": "0"})
    state = BatteryReader(root=root).read()
    assert state["cycle_count"] is None


def test_corrupt_values_do_not_raise(tmp_path):
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {
        "type": "Battery",
        "capacity": "not-a-number",
        "status": "Discharging",
        "power_now": "",
    })
    state = BatteryReader(root=root).read()
    assert state["present"] is True
    assert state["percent"] is None
    assert state["power_now_w"] is None


def test_eta_only_when_discharging_with_power(tmp_path):
    root = str(tmp_path)
    _mk_supply(root, "BAT0", {
        "type": "Battery",
        "capacity": "50",
        "status": "Charging",       # not discharging -> no eta
        "energy_now": "10000000",
        "power_now": "10000000",
    })
    state = BatteryReader(root=root).read()
    assert state["eta_seconds"] is None
