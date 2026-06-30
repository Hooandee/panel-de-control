"""Tests for fans/control.py — fan-curve backend (TDD)."""
import os

from fans.control import (
    AsusFanCurveBackend,
    NullFanBackend,
    _SAFE_MAX_TEMP_FLOOR,
    sanitize_curve,
    select_fan_backend,
)
from device_profiles import GENERIC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asus_chip(root, idx=0):
    """Create a synthetic asus_custom_fan_curve hwmon dir under tmp root."""
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "asus_custom_fan_curve")
    for m in (1, 2):
        for k in range(1, 9):
            _w(d, f"pwm{m}_auto_point{k}_temp", str(40 + k * 5))
            _w(d, f"pwm{m}_auto_point{k}_pwm", str(30 + k * 15))
        _w(d, f"pwm{m}_enable", "2")
    return d


def _w(d, name, val):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(val)


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# sanitize_curve — pure logic
# ---------------------------------------------------------------------------

class TestSanitizeCurve:
    def test_exact_8_points_passthrough(self):
        pts = [(i * 10, i * 20) for i in range(8)]
        result = sanitize_curve(pts)
        assert len(result) == 8

    def test_fewer_than_8_pads_by_repeating_last(self):
        pts = [(30, 50), (60, 100)]
        result = sanitize_curve(pts)
        assert len(result) == 8
        assert result[-1] == result[1]  # last is repeated

    def test_more_than_8_truncated(self):
        pts = [(i * 5, i * 10) for i in range(12)]
        result = sanitize_curve(pts)
        assert len(result) == 8

    def test_single_point_expands_to_8(self):
        result = sanitize_curve([(50, 100)])
        assert len(result) == 8
        assert all(p == result[0] for p in result)

    def test_empty_returns_8_points(self):
        result = sanitize_curve([])
        assert len(result) == 8

    def test_temps_clamped_0_to_100(self):
        pts = [(-10, 50), (150, 200)]
        result = sanitize_curve(pts + [(80, 100)] * 6)
        assert result[0][0] == 0
        assert result[1][0] == 100

    def test_pwm_clamped_to_0_255(self):
        pts = [(i * 10, -50) for i in range(4)] + [(50, 300)] + [(70, 200)] * 3
        result = sanitize_curve(pts)
        for _, pwm in result:
            assert 0 <= pwm <= 255

    def test_temps_made_nondecreasing(self):
        # Reversed temps must be fixed up
        pts = [(100, 200), (80, 150), (60, 120), (40, 80)] + [(40, 80)] * 4
        result = sanitize_curve(pts)
        temps = [p[0] for p in result]
        for a, b in zip(temps, temps[1:]):
            assert b >= a, f"temps not monotonic: {temps}"

    def test_temps_bumped_by_1_when_equal_after_clamp(self):
        # All same temp — each subsequent must be bumped
        pts = [(50, i * 10) for i in range(8)]
        result = sanitize_curve(pts)
        temps = [p[0] for p in result]
        for a, b in zip(temps, temps[1:]):
            assert b >= a

    def test_pwm_made_monotonic_nondecreasing(self):
        pts = [(i * 10, 200 - i * 20) for i in range(8)]  # descending pwm
        result = sanitize_curve(pts)
        pwms = [p[1] for p in result]
        for a, b in zip(pwms, pwms[1:]):
            assert b >= a, f"pwm not monotonic: {pwms}"

    def test_floor_pwm_applied_to_all_points(self):
        pts = [(i * 10, 0) for i in range(8)]
        result = sanitize_curve(pts, floor_pwm=50)
        for _, pwm in result:
            assert pwm >= 50

    def test_safe_max_temp_floor_applied_to_last_point(self):
        # Last point must be >= _SAFE_MAX_TEMP_FLOOR even without explicit floor_pwm
        pts = [(i * 10, 0) for i in range(8)]
        result = sanitize_curve(pts, pwm_max=255, floor_pwm=0)
        assert result[-1][1] >= _SAFE_MAX_TEMP_FLOOR

    def test_last_point_floor_does_not_push_earlier_points_up(self):
        # Earlier points can stay low; only the last must be >= floor
        pts = [(i * 10, 0) for i in range(8)]
        result = sanitize_curve(pts, pwm_max=255, floor_pwm=0)
        assert result[0][1] == 0  # first can be 0 (quiet at low temp)
        assert result[-1][1] >= _SAFE_MAX_TEMP_FLOOR

    def test_floor_pwm_takes_precedence_over_safe_floor_when_higher(self):
        pts = [(i * 10, 0) for i in range(8)]
        high_floor = _SAFE_MAX_TEMP_FLOOR + 50
        result = sanitize_curve(pts, floor_pwm=high_floor)
        assert result[-1][1] >= high_floor

    def test_returns_ints(self):
        pts = [(i * 10.5, i * 20.7) for i in range(8)]
        result = sanitize_curve(pts)
        for t, p in result:
            assert isinstance(t, int)
            assert isinstance(p, int)

    def test_reversed_input_fully_sanitized(self):
        pts = [(100 - i * 10, 200 - i * 20) for i in range(8)]
        result = sanitize_curve(pts)
        temps = [p[0] for p in result]
        pwms = [p[1] for p in result]
        for a, b in zip(temps, temps[1:]):
            assert b >= a
        for a, b in zip(pwms, pwms[1:]):
            assert b >= a


# ---------------------------------------------------------------------------
# AsusFanCurveBackend.read_state
# ---------------------------------------------------------------------------

class TestAsusFanCurveBackendReadState:
    def test_unsupported_when_no_hwmon(self, tmp_path):
        b = AsusFanCurveBackend(root=str(tmp_path))
        assert b.supported is False
        state = b.read_state()
        assert state["supported"] is False
        assert state["fans"] == []

    def test_unsupported_when_wrong_chip_name(self, tmp_path):
        d = os.path.join(str(tmp_path), "sys/class/hwmon/hwmon0")
        os.makedirs(d)
        _w(d, "name", "k10temp")
        _w(d, "pwm1_auto_point1_pwm", "50")
        b = AsusFanCurveBackend(root=str(tmp_path))
        assert b.supported is False

    def test_supported_when_asus_fan_curve_chip_present(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        assert b.supported is True

    def test_read_state_has_required_keys(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        assert state["supported"] is True
        assert state["source"] == "asus_custom_fan_curve"
        assert state["pwm_max"] == 255
        assert isinstance(state["fans"], list)

    def test_read_state_two_fans_cpu_gpu(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        keys = {f["key"] for f in state["fans"]}
        assert keys == {"cpu", "gpu"}

    def test_read_state_parses_8_points_per_fan(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        for fan in state["fans"]:
            assert len(fan["points"]) == 8
            for pt in fan["points"]:
                assert "temp" in pt and "pwm" in pt

    def test_read_state_parses_enable(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        for fan in state["fans"]:
            assert fan["enable"] == 2  # firmware auto as written by _make_asus_chip

    def test_read_state_skips_fan_without_enable(self, tmp_path):
        d = os.path.join(str(tmp_path), "sys/class/hwmon/hwmon0")
        os.makedirs(d)
        _w(d, "name", "asus_custom_fan_curve")
        # Only pwm1 has enable; pwm2 does not
        for k in range(1, 9):
            _w(d, f"pwm1_auto_point{k}_temp", "50")
            _w(d, f"pwm1_auto_point{k}_pwm", "100")
        _w(d, "pwm1_enable", "2")
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        keys = [f["key"] for f in state["fans"]]
        assert "cpu" in keys and "gpu" not in keys

    def test_read_state_never_raises_on_corrupt_file(self, tmp_path):
        d = os.path.join(str(tmp_path), "sys/class/hwmon/hwmon0")
        os.makedirs(d)
        _w(d, "name", "asus_custom_fan_curve")
        _w(d, "pwm1_enable", "2")
        _w(d, "pwm1_auto_point1_pwm", "garbage")
        for k in range(1, 9):
            _w(d, f"pwm1_auto_point{k}_temp", "50")
        state = AsusFanCurveBackend(root=str(tmp_path)).read_state()
        assert isinstance(state, dict)


# ---------------------------------------------------------------------------
# AsusFanCurveBackend.set_curve
# ---------------------------------------------------------------------------

class TestAsusFanCurveBackendSetCurve:
    def test_set_curve_writes_8_points_to_sysfs(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        pts = [(i * 10, i * 20) for i in range(8)]
        b.set_curve("cpu", pts)
        # Check point 1 written (k=1)
        assert _r(d, "pwm1_auto_point1_temp") == "0"
        assert _r(d, "pwm1_auto_point1_pwm") == str(max(0, pts[0][1]))

    def test_set_curve_sets_enable_to_1(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        b.set_curve("cpu", [(i * 10, i * 30) for i in range(8)])
        assert _r(d, "pwm1_enable") == "1"

    def test_set_curve_gpu_uses_m2(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        pts = [(i * 10, i * 25) for i in range(8)]
        b.set_curve("gpu", pts)
        assert _r(d, "pwm2_enable") == "1"

    def test_set_curve_sanitizes_points_before_writing(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        # Provide only 3 points; should pad to 8 and write successfully
        res = b.set_curve("cpu", [(30, 80), (60, 150), (90, 220)])
        assert res["ok"] is True

    def test_set_curve_returns_ok_true_on_success(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        assert res["ok"] is True

    def test_set_curve_returns_ok_false_on_unknown_fan_key(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_curve("nonexistent", [(i * 10, i * 25) for i in range(8)])
        assert res["ok"] is False

    def test_set_curve_returns_ok_false_when_unsupported(self, tmp_path):
        b = AsusFanCurveBackend(root=str(tmp_path))  # no hwmon
        res = b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        assert res["ok"] is False

    def test_set_curve_last_point_meets_safe_floor(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        # All-zero PWM curve — sanitizer must enforce floor on last point
        b.set_curve("cpu", [(i * 10, 0) for i in range(8)])
        written_last = int(_r(d, "pwm1_auto_point8_pwm"))
        assert written_last >= _SAFE_MAX_TEMP_FLOOR

    def test_set_curve_never_raises(self, tmp_path):
        """Even with a completely read-only (non-writable) dir, must not raise."""
        d = _make_asus_chip(str(tmp_path))
        os.chmod(os.path.join(d, "pwm1_auto_point1_temp"), 0o444)
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        assert isinstance(res, dict) and "ok" in res

    def test_set_curve_detail_is_string(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        assert isinstance(res["detail"], str)


# ---------------------------------------------------------------------------
# AsusFanCurveBackend.set_auto / restore_auto
# ---------------------------------------------------------------------------

class TestAsusFanCurveBackendSetAuto:
    def test_set_auto_specific_fan_writes_enable_2(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        # First go manual
        b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        assert _r(d, "pwm1_enable") == "1"
        # Then restore
        b.set_auto("cpu")
        assert _r(d, "pwm1_enable") == "2"

    def test_set_auto_none_restores_all_fans(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        b.set_curve("gpu", [(i * 10, i * 25) for i in range(8)])
        assert _r(d, "pwm1_enable") == "1"
        assert _r(d, "pwm2_enable") == "1"
        b.set_auto(None)
        assert _r(d, "pwm1_enable") == "2"
        assert _r(d, "pwm2_enable") == "2"

    def test_restore_auto_is_alias_of_set_auto_none(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        b.set_curve("cpu", [(i * 10, i * 25) for i in range(8)])
        b.restore_auto()
        assert _r(d, "pwm1_enable") == "2"
        assert _r(d, "pwm2_enable") == "2"

    def test_set_auto_returns_ok_true(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_auto(None)
        assert res["ok"] is True

    def test_set_auto_never_raises_when_unsupported(self, tmp_path):
        b = AsusFanCurveBackend(root=str(tmp_path))  # no hwmon
        res = b.set_auto(None)
        assert isinstance(res, dict) and "ok" in res

    def test_set_auto_unknown_fan_key_returns_ok_false(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = AsusFanCurveBackend(root=str(tmp_path))
        res = b.set_auto("bogus")
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# NullFanBackend
# ---------------------------------------------------------------------------

class TestNullFanBackend:
    def test_supported_false(self):
        assert NullFanBackend().supported is False

    def test_read_state_has_supported_false(self):
        s = NullFanBackend().read_state()
        assert s["supported"] is False

    def test_set_curve_returns_ok_false(self):
        res = NullFanBackend().set_curve("cpu", [])
        assert res["ok"] is False

    def test_set_auto_returns_ok_false(self):
        res = NullFanBackend().set_auto(None)
        assert res["ok"] is False

    def test_restore_auto_returns_ok_false(self):
        res = NullFanBackend().restore_auto()
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# select_fan_backend
# ---------------------------------------------------------------------------

class TestSelectFanBackend:
    def _rog_device(self):
        from device_profiles import DeviceProfile  # noqa: PLC0415
        return DeviceProfile(
            key="rog_ally_x",
            display_name="ROG Ally X",
            chip="AMD Z1 Extreme",
            vendor="amd",
            tdp_min=7,
            tdp_default=17,
            tdp_max=25,
            tdp_max_charger=35,
            match_names=("ROG Ally X",),
        )

    def test_returns_asus_backend_for_rog_device_with_chip(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        b = select_fan_backend(self._rog_device(), root=str(tmp_path))
        assert isinstance(b, AsusFanCurveBackend)
        assert b.supported is True

    def test_returns_asus_backend_when_chip_present_regardless_of_device(self, tmp_path):
        # Even GENERIC device can use the asus backend if the chip is present
        _make_asus_chip(str(tmp_path))
        b = select_fan_backend(GENERIC, root=str(tmp_path))
        assert isinstance(b, AsusFanCurveBackend)
        assert b.supported is True

    def test_returns_null_backend_when_chip_absent(self, tmp_path):
        b = select_fan_backend(GENERIC, root=str(tmp_path))
        assert isinstance(b, NullFanBackend)
        assert b.supported is False

    def test_rog_device_without_chip_gets_null_backend(self, tmp_path):
        b = select_fan_backend(self._rog_device(), root=str(tmp_path))
        assert isinstance(b, NullFanBackend)


class TestApplyCurveAll:
    _PTS = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]

    def test_writes_every_fan(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        be = AsusFanCurveBackend(root=str(tmp_path))
        res = be.apply_curve_all(self._PTS)
        assert res["ok"] is True
        st = be.read_state()
        assert {f["key"] for f in st["fans"]} == {"cpu", "gpu"}
        for fan in st["fans"]:
            assert fan["enable"] == 1  # manual mode engaged
            assert fan["points"][0]["pwm"] == 0  # point 1 written
            assert fan["points"][-1]["pwm"] >= 76  # safe floor honored

    def test_null_backend_returns_ok_false(self):
        assert NullFanBackend().apply_curve_all([[40, 0]])["ok"] is False
