import os

from battery.charge_limit import (
    LenovoConservationMode,
    NullChargeLimit,
    SteamDeckChargeLimit,
    SysfsChargeLimit,
    select_charge_limit,
)


def _mk_conservation(root, value="0"):
    d = os.path.join(root, "sys/devices/pci0000:00/PNP0C09:00/VPC2004:00")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "conservation_mode")
    with open(p, "w") as f:
        f.write(value)
    return p


def _mk_bat(root, with_threshold=True, value="100"):
    d = os.path.join(root, "sys/class/power_supply", "BAT0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "type"), "w") as f:
        f.write("Battery")
    if with_threshold:
        with open(os.path.join(d, "charge_control_end_threshold"), "w") as f:
            f.write(value)
    return d


def _mk_deck_hwmon(root, idx=3, value="0"):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write("steamdeck_hwmon")
    with open(os.path.join(d, "max_battery_charge_level"), "w") as f:
        f.write(value)
    return d


def test_unsupported_when_no_threshold_file(tmp_path):
    _mk_bat(str(tmp_path), with_threshold=False)
    cl = SysfsChargeLimit(root=str(tmp_path))
    assert cl.supported is False
    assert cl.get() is None


def test_reads_current_threshold(tmp_path):
    _mk_bat(str(tmp_path), value="80")
    cl = SysfsChargeLimit(root=str(tmp_path))
    assert cl.supported is True
    assert cl.get() == 80


def test_set_writes_and_readback_confirms(tmp_path):
    d = _mk_bat(str(tmp_path), value="100")
    cl = SysfsChargeLimit(root=str(tmp_path))
    assert cl.set(80) is True
    assert cl.get() == 80
    with open(os.path.join(d, "charge_control_end_threshold")) as f:
        assert f.read().strip() == "80"


def test_set_clamps_to_range(tmp_path):
    _mk_bat(str(tmp_path))
    cl = SysfsChargeLimit(root=str(tmp_path))
    lo, hi = cl.range()
    cl.set(hi + 50)
    assert cl.get() == hi
    cl.set(lo - 50)
    assert cl.get() == lo


def test_sysfs_disable_writes_max(tmp_path):
    _mk_bat(str(tmp_path), value="80")
    cl = SysfsChargeLimit(root=str(tmp_path))
    assert cl.disable() is True
    assert cl.get() == 100  # 100 = no cap on ASUS/Lenovo


def test_null_backend_is_unsupported():
    cl = NullChargeLimit()
    assert cl.supported is False
    assert cl.get() is None
    assert cl.set(80) is False
    assert cl.disable() is False


# --- Steam Deck (max_battery_charge_level; 0 = no cap) ---

def test_deck_reads_and_sets_level(tmp_path):
    _mk_deck_hwmon(str(tmp_path), value="0")
    cl = SteamDeckChargeLimit(root=str(tmp_path))
    assert cl.supported is True
    assert cl.get() == 0
    assert cl.set(80) is True
    assert cl.get() == 80


def test_deck_disable_writes_zero(tmp_path):
    _mk_deck_hwmon(str(tmp_path), value="80")
    cl = SteamDeckChargeLimit(root=str(tmp_path))
    assert cl.disable() is True
    assert cl.get() == 0  # 0 = no cap on the Deck


def test_deck_unsupported_without_chip(tmp_path):
    cl = SteamDeckChargeLimit(root=str(tmp_path))
    assert cl.supported is False


def test_select_returns_null_when_absent(tmp_path):
    _mk_bat(str(tmp_path), with_threshold=False)

    class Dev:
        key = "rog_ally_x"

    cl = select_charge_limit(Dev(), root=str(tmp_path))
    assert cl.supported is False


def test_select_returns_sysfs_for_asus(tmp_path):
    _mk_bat(str(tmp_path), value="90")

    class Dev:
        key = "rog_ally_x"

    cl = select_charge_limit(Dev(), root=str(tmp_path))
    assert isinstance(cl, SysfsChargeLimit)
    assert cl.get() == 90


# --- Lenovo conservation mode (boolean, fixed cap, not adjustable) ---

def test_lenovo_conservation_is_boolean_toggle(tmp_path):
    _mk_conservation(str(tmp_path), value="0")
    cl = LenovoConservationMode(root=str(tmp_path))
    assert cl.supported is True
    assert cl.adjustable is False
    assert cl.get() is None  # no known percent read from sysfs
    assert cl.fixed_percent == 80  # firmware conservation level, surfaced to the UI
    assert cl.set(80) is True  # percent ignored -> writes 1 (on)
    assert cl.disable() is True


def test_lenovo_conservation_unsupported_without_file(tmp_path):
    cl = LenovoConservationMode(root=str(tmp_path))
    assert cl.supported is False


def test_lenovo_conservation_found_via_acpi_flat_path(tmp_path):
    # The stable flat ACPI location (no recursive /sys/devices walk).
    d = os.path.join(str(tmp_path), "sys/bus/acpi/devices/VPC2004:00")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "conservation_mode"), "w") as f:
        f.write("1")
    cl = LenovoConservationMode(root=str(tmp_path))
    assert cl.supported is True
    assert cl.disable() is True


def test_sysfs_is_adjustable(tmp_path):
    _mk_bat(str(tmp_path), value="80")
    assert SysfsChargeLimit(root=str(tmp_path)).adjustable is True


def test_select_legion_falls_back_to_conservation(tmp_path):
    # No standard threshold present, only conservation_mode.
    _mk_conservation(str(tmp_path), value="0")

    class Dev:
        key = "legion_go_2"

    cl = select_charge_limit(Dev(), root=str(tmp_path))
    assert isinstance(cl, LenovoConservationMode)
    assert cl.adjustable is False


def test_select_returns_deck_backend_for_deck(tmp_path):
    _mk_deck_hwmon(str(tmp_path), value="0")

    class Dev:
        key = "steam_deck_oled"

    cl = select_charge_limit(Dev(), root=str(tmp_path))
    assert isinstance(cl, SteamDeckChargeLimit)
    assert cl.supported is True


class _Generic:
    key = "generic"


def test_select_generic_uses_standard_threshold(tmp_path):
    _mk_bat(str(tmp_path), value="85")
    cl = select_charge_limit(_Generic(), root=str(tmp_path))
    assert isinstance(cl, SysfsChargeLimit)
    assert cl.get() == 85


def test_select_generic_finds_conservation_mode(tmp_path):
    _mk_conservation(str(tmp_path), value="0")
    cl = select_charge_limit(_Generic(), root=str(tmp_path))
    assert isinstance(cl, LenovoConservationMode)


def test_select_generic_finds_deck_level(tmp_path):
    _mk_deck_hwmon(str(tmp_path), value="0")
    cl = select_charge_limit(_Generic(), root=str(tmp_path))
    assert isinstance(cl, SteamDeckChargeLimit)
