"""Tests for the MSI Claw fan-curve backend (msi_wmi_platform hwmon, 6 points x
2 fans) and the generalized N-point sanitize. Synthetic sysfs — no hardware."""
import os

from fans.control import (
    MsiFanCurveBackend,
    NullFanBackend,
    _SAFE_MAX_TEMP_FLOOR,
    sanitize_curve,
    select_fan_backend,
)

MSI_TEMPS = (0, 50, 60, 70, 80, 88)


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(val)


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _make_msi_chip(root, idx=0):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "msi_wmi_platform")
    for m in (1, 2):
        for k in range(1, 7):  # MSI exposes 6 curve points
            _w(d, f"pwm{m}_auto_point{k}_temp", str(MSI_TEMPS[k - 1]))
            _w(d, f"pwm{m}_auto_point{k}_pwm", str(20 * k))
        _w(d, f"pwm{m}_enable", "2")
    return d


# A canonical 8-point curve (what the curve editor stores) — must be resampled to MSI's 6.
CANON_8 = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


class TestSanitizeNPoints:
    def test_sanitize_to_6_points(self):
        result = sanitize_curve(CANON_8, n_points=6)
        assert len(result) == 6
        assert result[-1][1] >= _SAFE_MAX_TEMP_FLOOR


class TestMsiBackend:
    def test_supported_when_chip_present(self, tmp_path):
        _make_msi_chip(str(tmp_path))
        assert MsiFanCurveBackend(root=str(tmp_path)).supported is True

    def test_read_state_reports_six_point_fans(self, tmp_path):
        _make_msi_chip(str(tmp_path))
        st = MsiFanCurveBackend(root=str(tmp_path)).read_state()
        assert st["supported"] is True
        assert st["source"] == "msi_wmi_platform"
        assert len(st["fans"]) == 2
        assert len(st["fans"][0]["points"]) == 6

    def test_apply_curve_resamples_to_msi_temps_and_enables_manual(self, tmp_path):
        d = _make_msi_chip(str(tmp_path))
        res = MsiFanCurveBackend(root=str(tmp_path)).apply_curve_all(CANON_8)
        assert res["ok"] is True
        # both fans switched to manual
        assert _r(d, "pwm1_enable") == "1"
        assert _r(d, "pwm2_enable") == "1"
        # written temps are MSI's fixed 6 anchors
        written_temps = [int(_r(d, f"pwm1_auto_point{k}_temp")) for k in range(1, 7)]
        assert written_temps == list(MSI_TEMPS)
        # pwm monotonic non-decreasing + hot-point safety floor
        written_pwm = [int(_r(d, f"pwm1_auto_point{k}_pwm")) for k in range(1, 7)]
        assert written_pwm == sorted(written_pwm)
        assert written_pwm[-1] >= _SAFE_MAX_TEMP_FLOOR

    def test_set_auto_restores_firmware(self, tmp_path):
        d = _make_msi_chip(str(tmp_path))
        b = MsiFanCurveBackend(root=str(tmp_path))
        b.apply_curve_all(CANON_8)
        b.set_auto(None)
        assert _r(d, "pwm1_enable") == "2"
        assert _r(d, "pwm2_enable") == "2"

    def test_factory_selects_msi_when_only_msi_present(self, tmp_path):
        _make_msi_chip(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path))
        assert isinstance(backend, MsiFanCurveBackend)

    def test_factory_null_when_no_chip(self, tmp_path):
        assert isinstance(select_fan_backend(None, root=str(tmp_path)), NullFanBackend)
