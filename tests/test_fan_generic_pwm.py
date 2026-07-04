"""Generic hwmon PWM fan backend — last-resort software loop for handhelds whose
fan chip exposes the standard manual-PWM interface (pwmN + pwmN_enable) but no
vendor curve-table. Synthetic sysfs; the asyncio loop isn't exercised (start() is
a no-op without a running loop) — the seams are the immediate apply + release."""
import os

from fans.generic_pwm import GenericPwmFanBackend
from fans.control import NullFanBackend, select_fan_backend


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(str(val))


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _mk_pwm_chip(root, idx=0, name="generic_ec", fans=(1,), enable="2"):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", name)
    for m in fans:
        _w(d, f"pwm{m}", "0")
        _w(d, f"pwm{m}_enable", enable)
        _w(d, f"fan{m}_input", "1800")
    return d


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _backend(root, temp=70.0):
    return GenericPwmFanBackend(root=str(root), temp_fn=lambda: temp)


def test_unsupported_without_pwm(tmp_path):
    assert _backend(tmp_path).supported is False


def test_unsupported_when_pwm_has_no_real_fan(tmp_path):
    # A pwm with no fanN_input on the chip is not trusted to drive a real fan.
    d = os.path.join(str(tmp_path), "sys/class/hwmon/hwmon0")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "mystery")
    _w(d, "pwm1", "0")
    _w(d, "pwm1_enable", "2")
    assert _backend(tmp_path).supported is False


def test_supported_with_pwm_and_fan(tmp_path):
    _mk_pwm_chip(str(tmp_path))
    assert _backend(tmp_path).supported is True


def test_read_state_reports_fan(tmp_path):
    _mk_pwm_chip(str(tmp_path))
    st = _backend(tmp_path).read_state()
    assert st["supported"] is True
    assert st["fans"] and st["fans"][0]["rpm"] == 1800


def test_apply_switches_to_manual_and_writes_curve_pwm(tmp_path):
    d = _mk_pwm_chip(str(tmp_path))
    b = _backend(tmp_path, temp=70.0)
    res = b.apply_curve_all(CURVE)
    assert res["ok"] is True
    assert _r(d, "pwm1_enable") == "1"
    assert int(_r(d, "pwm1")) == 95  # curve pwm at 70C


def test_hot_point_keeps_safety_floor(tmp_path):
    # A curve pushed to 0% everywhere still writes >=76 at the hottest point.
    d = _mk_pwm_chip(str(tmp_path))
    b = _backend(tmp_path, temp=95.0)
    b.apply_curve_all([(40, 0), (95, 0)])
    assert int(_r(d, "pwm1")) >= 76


def test_cool_temp_allows_zero_pwm(tmp_path):
    d = _mk_pwm_chip(str(tmp_path))
    b = _backend(tmp_path, temp=40.0)
    b.apply_curve_all(CURVE)
    assert int(_r(d, "pwm1")) == 0  # fan off when cold is legitimate


def test_set_auto_restores_original_enable(tmp_path):
    d = _mk_pwm_chip(str(tmp_path), enable="2")
    b = _backend(tmp_path, temp=70.0)
    b.apply_curve_all(CURVE)
    b.set_auto(None)
    assert _r(d, "pwm1_enable") == "2"


def test_temp_none_releases_to_auto(tmp_path):
    d = _mk_pwm_chip(str(tmp_path))
    b = GenericPwmFanBackend(root=str(tmp_path), temp_fn=lambda: None)
    b.apply_curve_all(CURVE)
    # No safe temp reading → hand back to firmware rather than hold a stale pwm.
    assert _r(d, "pwm1_enable") == "2"


def test_multi_fan_all_driven(tmp_path):
    d = _mk_pwm_chip(str(tmp_path), fans=(1, 2))
    b = _backend(tmp_path, temp=80.0)
    b.apply_curve_all(CURVE)
    assert _r(d, "pwm1_enable") == "1" and _r(d, "pwm2_enable") == "1"
    assert int(_r(d, "pwm1")) == 135 and int(_r(d, "pwm2")) == 135


def test_factory_selects_generic_pwm_last(tmp_path):
    _mk_pwm_chip(str(tmp_path))
    backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0)
    assert isinstance(backend, GenericPwmFanBackend)


def test_factory_null_when_nothing(tmp_path):
    assert isinstance(select_fan_backend(None, root=str(tmp_path)), NullFanBackend)
