"""Tests for the Legion Go legion_wmi_fan hwmon curve backend.

The chip exposes ``pwm1_enable`` (1=manual, 2=auto) and a 10-point
``pwm1_auto_point{1..10}_pwm`` curve at fixed temperature anchors [10..100];
the temp point files are not writable, only the pwm points are written.
"""
import os

from fans.control import (
    LegionWmiFanBackend,
    NullFanBackend,
    _SAFE_MAX_TEMP_FLOOR,
    select_fan_backend,
)
from device_profiles import GENERIC, DeviceProfile


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(val)


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _make_legion_chip(root, idx=0):
    """Synthetic legion_wmi_fan hwmon: one fan, 10 pwm points, no temp files."""
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "legion_wmi_fan")
    _w(d, "fan1_input", "3200")
    for k in range(1, 11):
        _w(d, f"pwm1_auto_point{k}_pwm", str(100 + k * 10))
    _w(d, "pwm1_enable", "2")
    return d


def _legion_device():
    return DeviceProfile(
        key="legion_go", display_name="Legion Go", chip="AMD Z1 Extreme",
        vendor="amd", tdp_min=5, tdp_default=15, tdp_max=30, tdp_max_charger=30,
        match_names=("83E1", "Legion Go"),
    )


class TestSupported:
    def test_unsupported_when_no_hwmon(self, tmp_path):
        assert LegionWmiFanBackend(root=str(tmp_path)).supported is False

    def test_supported_when_chip_present(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        assert LegionWmiFanBackend(root=str(tmp_path)).supported is True

    def test_source_name_is_chip(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        assert LegionWmiFanBackend(root=str(tmp_path)).read_state()["source"] == "legion_wmi_fan"


class TestReadState:
    def test_single_fan_ten_points(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        st = LegionWmiFanBackend(root=str(tmp_path)).read_state()
        assert st["supported"] is True
        assert len(st["fans"]) == 1
        assert len(st["fans"][0]["points"]) == 10

    def test_temps_none_when_driver_exposes_no_temp_files(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        st = LegionWmiFanBackend(root=str(tmp_path)).read_state()
        temps = [p["temp"] for p in st["fans"][0]["points"]]
        assert all(t is None for t in temps)


class TestSetCurve:
    _PTS = [(10, 110), (20, 120), (30, 130), (40, 140), (50, 150),
            (60, 160), (70, 170), (80, 180), (90, 200), (100, 255)]

    def test_writes_pwm_points_without_temp_files(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))  # no temp files
        res = LegionWmiFanBackend(root=str(tmp_path)).set_curve("fan", self._PTS)
        assert res["ok"] is True
        assert _r(d, "pwm1_auto_point1_pwm") == "110"
        assert not os.path.exists(os.path.join(d, "pwm1_auto_point1_temp"))

    def test_sets_enable_manual(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))
        LegionWmiFanBackend(root=str(tmp_path)).set_curve("fan", self._PTS)
        assert _r(d, "pwm1_enable") == "1"

    def test_last_point_meets_safe_floor(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))
        LegionWmiFanBackend(root=str(tmp_path)).set_curve("fan", [(t, 0) for t in range(10, 110, 10)])
        assert int(_r(d, "pwm1_auto_point10_pwm")) >= _SAFE_MAX_TEMP_FLOOR

    def test_never_writes_temp_files(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))
        LegionWmiFanBackend(root=str(tmp_path)).set_curve("fan", self._PTS)
        assert not os.path.exists(os.path.join(d, "pwm1_auto_point5_temp"))

    def test_apply_curve_all(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))
        res = LegionWmiFanBackend(root=str(tmp_path)).apply_curve_all(self._PTS)
        assert res["ok"] is True
        assert _r(d, "pwm1_enable") == "1"

    def test_never_raises_unsupported(self, tmp_path):
        res = LegionWmiFanBackend(root=str(tmp_path)).set_curve("fan", self._PTS)
        assert res["ok"] is False


class TestSetAuto:
    def test_restores_firmware_auto(self, tmp_path):
        d = _make_legion_chip(str(tmp_path))
        b = LegionWmiFanBackend(root=str(tmp_path))
        b.apply_curve_all([(t, 200) for t in range(10, 110, 10)])
        assert _r(d, "pwm1_enable") == "1"
        b.restore_auto()
        assert _r(d, "pwm1_enable") == "2"


class TestSelectFanBackend:
    def test_selected_when_chip_present(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        b = select_fan_backend(_legion_device(), root=str(tmp_path))
        assert isinstance(b, LegionWmiFanBackend)
        assert b.supported is True

    def test_chip_detected_regardless_of_device(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        b = select_fan_backend(GENERIC, root=str(tmp_path))
        assert isinstance(b, LegionWmiFanBackend)

    def test_null_when_chip_absent(self, tmp_path):
        b = select_fan_backend(_legion_device(), root=str(tmp_path))
        assert isinstance(b, NullFanBackend)
