import os

from device_profiles import DEVICE_TABLE, GENERIC
from fans.control import ZotacFanReadOnlyBackend, select_fan_backend
from fans.generic_pwm import GenericPwmFanBackend


ZOTAC = next(profile for profile in DEVICE_TABLE if profile.key == "zotac_gaming_zone")


def _write(directory, name, value):
    with open(os.path.join(directory, name), "w") as handle:
        handle.write(str(value))


def _make_zotac(root, points=9):
    directory = os.path.join(root, "sys/class/hwmon/hwmon0")
    os.makedirs(directory, exist_ok=True)
    _write(directory, "name", "zotac_platform")
    _write(directory, "fan1_input", 3600)
    _write(directory, "pwm1", 176)
    _write(directory, "pwm1_enable", 2)
    for point in range(1, points + 1):
        _write(directory, f"pwm1_auto_point{point}_temp", 30 + point * 5)
        _write(directory, f"pwm1_auto_point{point}_pwm", 20 + point * 5)
    return directory


def _snapshot(directory):
    return {
        name: open(os.path.join(directory, name)).read()
        for name in os.listdir(directory)
    }


def test_zotac_stays_read_only_even_when_full_curve_contract_exists(tmp_path):
    directory = _make_zotac(str(tmp_path))
    before = _snapshot(directory)

    backend = select_fan_backend(ZOTAC, root=str(tmp_path))

    assert isinstance(backend, ZotacFanReadOnlyBackend)
    assert backend.read_state()["source"] == "zotac-firmware-auto"
    assert backend.set_curve("fan", [(40, 255)])["ok"] is False
    assert backend.set_auto()["ok"] is False
    assert _snapshot(directory) == before


def test_zotac_incomplete_contract_never_falls_into_generic_writer(tmp_path):
    directory = _make_zotac(str(tmp_path), points=8)
    before = _snapshot(directory)

    backend = select_fan_backend(ZOTAC, root=str(tmp_path))

    assert isinstance(backend, ZotacFanReadOnlyBackend)
    assert backend.apply_curve_all([(40, 255)])["ok"] is False
    assert _snapshot(directory) == before


def test_same_chip_on_unknown_device_keeps_existing_capability_fallback(tmp_path):
    _make_zotac(str(tmp_path))

    assert isinstance(
        select_fan_backend(GENERIC, root=str(tmp_path)),
        GenericPwmFanBackend,
    )
