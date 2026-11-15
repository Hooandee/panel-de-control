import os
import re

import pytest

import fans.generic_pwm as generic_pwm
from device_profiles import DESKTOP_PC
from fans.control import NullFanBackend, select_fan_backend
from fans.generic_pwm import GenericPwmFanBackend
from fans.presets import RESOLVED

CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]
GPU_DRIVERS = ("amdgpu", "radeon", "nouveau", "i915", "xe")


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(str(val))


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _chip(root, idx=0, name="generic_ec", fans=(1,), enable="2", tach=True):
    d = os.path.join(str(root), "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", name)
    for m in fans:
        _w(d, f"pwm{m}", "0")
        _w(d, f"pwm{m}_enable", enable)
        if tach:
            _w(d, f"fan{m}_input", "1800")
    return d


def _backend(root, temp=70.0):
    return GenericPwmFanBackend(root=str(root), temp_fn=lambda: temp)


def _strict_driver(monkeypatch):
    real_write = generic_pwm._write

    def strict_write(path, value):
        m = re.match(r"pwm(\d+)$", os.path.basename(path))
        if m:
            enable = os.path.join(os.path.dirname(path), f"pwm{m.group(1)}_enable")
            try:
                with open(enable) as f:
                    if f.read().strip() != "1":
                        return False
            except OSError:
                return False
        return real_write(path, value)

    monkeypatch.setattr(generic_pwm, "_write", strict_write)


@pytest.mark.parametrize("chips", [
    pytest.param([], id="no-hwmon"),
    pytest.param([dict(name="mystery", tach=False)], id="pwm-without-tach"),
    pytest.param([dict(idx=3, name="nct6798", tach=False)], id="tachless-board-chip"),
    pytest.param([dict(idx=i, name=n) for i, n in enumerate(GPU_DRIVERS)], id="discrete-gpu-only"),
])
def test_chips_that_are_never_driven(tmp_path, chips):
    for chip in chips:
        _chip(tmp_path, **chip)
    assert _backend(tmp_path).supported is False
    assert isinstance(select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0),
                      NullFanBackend)


@pytest.mark.parametrize("temp, curve, fans, check", [
    pytest.param(70.0, CURVE, (1,), lambda duty: duty == 95, id="interpolated"),
    pytest.param(40.0, CURVE, (1,), lambda duty: duty == 0, id="cold-allows-zero"),
    pytest.param(95.0, [(40, 0), (95, 0)], (1,), lambda duty: duty >= 76, id="hot-safety-floor"),
    pytest.param(80.0, CURVE, (1, 2), lambda duty: duty == 135, id="every-fan"),
])
def test_apply_engages_manual_and_writes_the_curve_duty(tmp_path, temp, curve, fans, check):
    d = _chip(tmp_path, fans=fans)
    backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: temp)
    assert isinstance(backend, GenericPwmFanBackend)
    assert backend.read_state()["fans"][0]["rpm"] == 1800
    assert backend.apply_curve_all(curve)["ok"] is True
    for m in fans:
        assert _r(d, f"pwm{m}_enable") == "1"
        assert check(int(_r(d, f"pwm{m}")))
    backend.set_auto(None)
    assert all(_r(d, f"pwm{m}_enable") == "2" for m in fans)


@pytest.mark.parametrize("name, auto, temp, duty", [
    pytest.param("gpdfan", "2", 70.0, 95, id="gpd_fan"),
    pytest.param("oxpec", "0", 80.0, 135, id="oxp-auto-sentinel-0"),
])
def test_strict_driver_gets_manual_before_duty_and_its_own_auto_back(
        tmp_path, monkeypatch, name, auto, temp, duty):
    d = _chip(tmp_path, name=name, enable=auto)
    _strict_driver(monkeypatch)
    backend = _backend(tmp_path, temp=temp)
    assert backend.apply_curve_all(CURVE)["ok"] is True
    assert _r(d, "pwm1_enable") == "1"
    assert int(_r(d, "pwm1")) == duty
    backend.set_auto(None)
    assert _r(d, "pwm1_enable") == auto


def test_missing_temperature_releases_to_auto(tmp_path):
    d = _chip(tmp_path)
    GenericPwmFanBackend(root=str(tmp_path), temp_fn=lambda: None).apply_curve_all(CURVE)
    assert _r(d, "pwm1_enable") == "2"


def test_read_state_enable_follows_the_mode_readback_not_the_tach(tmp_path):
    d = _chip(tmp_path)
    backend = _backend(tmp_path)
    assert backend.read_state()["fans"][0]["enable"] == 2
    _w(d, "fan1_input", "0")
    backend.apply_curve_all(CURVE)
    assert backend.read_state()["fans"][0]["enable"] == 1
    _w(d, "fan1_input", "1800")
    _w(d, "pwm1_enable", "2")
    assert backend.read_state()["fans"][0]["enable"] == 2


def test_partial_write_rolls_the_failed_fan_back_to_firmware(tmp_path):
    d = _chip(tmp_path, fans=(1, 2))
    os.chmod(os.path.join(d, "pwm2"), 0o444)
    backend = _backend(tmp_path, temp=80.0)
    assert backend.apply_curve_all(CURVE)["ok"] is False
    assert {f["key"]: f["enable"] for f in backend.read_state()["fans"]} == {"fan1": 1, "fan2": 2}
    assert _r(d, "pwm2_enable") == "2"


def test_discrete_gpu_chip_is_skipped_for_the_system_fan_chip(tmp_path):
    gpu = _chip(tmp_path, idx=0, name="amdgpu")
    board = _chip(tmp_path, idx=1, name="nct6798")
    backend = _backend(tmp_path)
    assert backend.supported is True
    backend.set_curve("fan1", CURVE)
    assert _r(board, "pwm1_enable") == "1"
    assert (_r(gpu, "pwm1_enable"), _r(gpu, "pwm1")) == ("2", "0")


def test_desktop_drives_only_spinning_board_headers_above_the_floor(tmp_path):
    gpu = _chip(tmp_path, idx=0, name="amdgpu")
    board = _chip(tmp_path, idx=1, name="nct6798", fans=(1, 2, 3), enable="5")
    _w(board, "fan3_input", "0")
    backend = select_fan_backend(DESKTOP_PC, root=str(tmp_path), temp_fn=lambda: 30.0)

    assert isinstance(backend, GenericPwmFanBackend)
    backend.set_curve("fan1", CURVE)
    assert [_r(board, f"pwm{m}_enable") for m in (1, 2, 3)] == ["1", "1", "5"]
    assert int(_r(board, "pwm1")) == 77
    assert _r(board, "pwm3") == "0"
    assert _r(gpu, "pwm1_enable") == "2"

    backend.restore_auto()
    assert [_r(board, f"pwm{m}_enable") for m in (1, 2)] == ["5", "5"]


def test_desktop_without_board_fans_is_read_only(tmp_path):
    _chip(tmp_path, name="amdgpu")
    assert isinstance(select_fan_backend(DESKTOP_PC, root=str(tmp_path)), NullFanBackend)


def _pwm_fan_board(root, bound=False):
    chip = _chip(root, name="pwmfan", enable="3")
    thermal = os.path.join(str(root), "sys/class/thermal")
    cooling = os.path.join(thermal, "cooling_device3")
    os.makedirs(cooling)
    _w(cooling, "type", "pwm-fan")
    zone = os.path.join(thermal, "thermal_zone0")
    os.makedirs(zone)
    if bound:
        os.symlink("../cooling_device3", os.path.join(zone, "cdev0"))
    return chip


@pytest.mark.parametrize("make, expected", [
    pytest.param(_chip, True, id="pc-fan-chip"),
    pytest.param(lambda root: _pwm_fan_board(root, bound=True), True, id="pwm-fan-thermally-bound"),
    pytest.param(_pwm_fan_board, False, id="pwm-fan-unbound"),
])
def test_firmware_automatic_exists_only_where_something_else_drives_the_fan(tmp_path, make, expected):
    make(tmp_path)
    backend = _backend(tmp_path)
    assert backend.firmware_auto is expected
    assert backend.set_auto()["ok"] is True


def test_without_a_firmware_automatic_auto_runs_panels_curve_and_release_keeps_it_spinning(tmp_path):
    chip = _pwm_fan_board(tmp_path)
    backend = _backend(tmp_path, temp=70.0)
    assert backend.set_auto()["ok"] is True
    assert _r(chip, "pwm1_enable") == "1"
    assert int(_r(chip, "pwm1")) == dict(RESOLVED["balanced"])[70]

    assert backend.restore_auto()["ok"] is True
    assert _r(chip, "pwm1_enable") == "1"
    assert _r(chip, "pwm1") == str(generic_pwm.FAILSAFE_DUTY)
