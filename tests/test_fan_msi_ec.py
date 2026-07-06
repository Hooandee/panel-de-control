"""MSI Claw 8 AI+ raw-EC fan backend (register 0x33 step control).

Tests inject a FakeEC (dict-backed) + a synthetic DMI so no hardware is touched.
0x33 encoding: low nibble 0 = manual, high nibble = speed level; 0x05 = release
to firmware auto.
"""
import os

from fans.msi_ec import (
    MsiEcFanBackend,
    pwm_to_ec_byte,
    EC_AUTO,
    EC_LEVELS,
    REG_FAN,
    REG_RPM_A,
    _SAFE_HOT_TEMP_C,
    _SAFE_MIN_HOT_BYTE,
)
from fans.control import select_fan_backend, NullFanBackend


class FakeEC:
    """dict-backed EC; mirrors the real _EcSys read/write surface."""

    def __init__(self, writable=True):
        self.mem = {}
        self._writable = writable

    def writable(self):
        return self._writable

    def read(self, addr):
        return self.mem.get(addr)

    def write(self, addr, val):
        if not self._writable:
            return False
        self.mem[addr] = val & 0xFF
        return True


def _dmi(root, vendor="Micro-Star International Co., Ltd.", name="MS-1T81"):
    d = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(d, exist_ok=True)
    for fname, val in (("sys_vendor", vendor), ("product_name", name)):
        with open(os.path.join(d, fname), "w") as f:
            f.write(val)


# 8-point canonical curve: cool→quiet, hot→full.
CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _backend(root, ec, temp=70.0):
    return MsiEcFanBackend(root=str(root), ec=ec, temp_fn=lambda: temp)


# --- pure mapping ---------------------------------------------------------

class TestPwmToEcByte:
    def test_zero_pwm_maps_to_lowest_manual_level(self):
        # low nibble 0 = manual; high nibble 0 = slowest level. NOT release.
        b = pwm_to_ec_byte(0)
        assert b & 0x0F == 0            # manual (low nibble 0)
        assert b == EC_LEVELS[0]

    def test_max_pwm_maps_to_top_level(self):
        assert pwm_to_ec_byte(255) == EC_LEVELS[-1]

    def test_result_is_always_a_known_level(self):
        for pwm in range(0, 256):
            assert pwm_to_ec_byte(pwm) in EC_LEVELS

    def test_low_nibble_always_manual(self):
        for pwm in range(0, 256, 7):
            assert pwm_to_ec_byte(pwm) & 0x0F == 0

    def test_monotonic_nondecreasing(self):
        prev = -1
        for pwm in range(0, 256):
            cur = pwm_to_ec_byte(pwm)
            assert cur >= prev
            prev = cur

    def test_nearest_level_selection(self):
        # A pwm just above a level's midpoint rounds up to the next level.
        # Levels evenly span 0..255 across len(EC_LEVELS) buckets.
        lo, hi = EC_LEVELS[0], EC_LEVELS[1]
        # midpoint pwm between bucket 0 and 1
        step = 255 / (len(EC_LEVELS) - 1)
        assert pwm_to_ec_byte(int(step * 0.4)) == lo
        assert pwm_to_ec_byte(int(step * 0.6)) == hi


# --- backend --------------------------------------------------------------

class TestMsiEcBackend:
    def test_supported_when_msi_and_ec_writable(self, tmp_path):
        _dmi(str(tmp_path))
        assert _backend(tmp_path, FakeEC()).supported is True

    def test_unsupported_when_not_msi(self, tmp_path):
        _dmi(str(tmp_path), vendor="ASUSTeK COMPUTER INC.", name="RC71L")
        assert _backend(tmp_path, FakeEC()).supported is False

    def test_unsupported_when_ec_not_writable(self, tmp_path):
        _dmi(str(tmp_path))
        assert _backend(tmp_path, FakeEC(writable=False)).supported is False

    def test_apply_writes_manual_level(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec, temp=85.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        written = ec.read(REG_FAN)
        assert written == b.target_for_temp(85.0)
        assert written & 0x0F == 0        # manual
        assert written in EC_LEVELS

    def test_set_auto_writes_release_sentinel(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert ec.read(REG_FAN) == EC_AUTO

    def test_cool_point_stays_manual_not_release(self, tmp_path):
        # 40C → CURVE duty 0 → lowest manual level (0x00), which must NOT collide
        # with the release sentinel (0x05). A driven cool point stays manual.
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec, temp=40.0)
        b.apply_curve_all(CURVE)
        written = ec.read(REG_FAN)
        assert written != EC_AUTO
        assert written & 0x0F == 0

    def test_safety_floor_forces_high_level_when_hot(self, tmp_path):
        # A curve that stays quiet even when hot: above the hot-temp threshold the
        # driven level is clamped up regardless of the curve.
        _dmi(str(tmp_path))
        ec = FakeEC()
        quiet = [(t, 0) for t in (40, 50, 60, 70, 80, 85, 90, 95)]
        b = _backend(tmp_path, ec, temp=_SAFE_HOT_TEMP_C + 5)
        b.apply_curve_all(quiet)
        assert ec.read(REG_FAN) >= _SAFE_MIN_HOT_BYTE

    def test_safety_floor_engages_at_threshold(self, tmp_path):
        # The clamp is a °C threshold, not a pwm value: it engages exactly at
        # _SAFE_HOT_TEMP_C even for a curve whose duty there discretizes low.
        _dmi(str(tmp_path))
        quiet = [(t, 0) for t in (40, 50, 60, 70, 80, 85, 90, 95)]
        b = _backend(tmp_path, FakeEC(), temp=_SAFE_HOT_TEMP_C)
        b.apply_curve_all(quiet)
        assert b.target_for_temp(_SAFE_HOT_TEMP_C) >= _SAFE_MIN_HOT_BYTE
        # Just below the threshold the curve is honored (not force-clamped).
        assert b.target_for_temp(_SAFE_HOT_TEMP_C - 1) == pwm_to_ec_byte(0)

    def test_read_rpm_decodes(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        ec.write(REG_RPM_A, 130)  # 480000/130 = 3692 rpm
        st = _backend(tmp_path, ec).read_state()
        assert st["fans"][0]["rpm"] == 480000 // 130

    def test_read_rpm_none_when_zero_or_missing(self, tmp_path):
        _dmi(str(tmp_path))
        # missing register → None (honest), not a divide-by-zero.
        st = _backend(tmp_path, FakeEC()).read_state()
        assert st["fans"][0]["rpm"] is None

    def test_apply_fails_honestly_when_write_blocked(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC(writable=False)
        b = _backend(tmp_path, ec, temp=70.0)
        # unsupported → apply refuses (returns ok=False)
        assert b.apply_curve_all(CURVE)["ok"] is False

    def test_target_monotonic_in_range(self, tmp_path):
        _dmi(str(tmp_path))
        b = _backend(tmp_path, FakeEC())
        b.apply_curve_all(CURVE)
        assert EC_LEVELS[0] <= b.target_for_temp(45) <= b.target_for_temp(90) <= EC_LEVELS[-1]

    def test_factory_does_not_wire_msi_ec_even_when_writable(self, tmp_path):
        # The EC step backend is deliberately not selected: its top step resets
        # the Claw. Even with a writable EC the factory keeps firmware auto (Null).
        _dmi(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0,
                                     ec=FakeEC())
        assert isinstance(backend, NullFanBackend)

    def test_factory_null_when_ec_readonly_and_no_hwmon(self, tmp_path):
        # MSI vendor but EC not writable and no msi_wmi_platform hwmon → Null
        # (honest: no controllable path). firmware-curve read handled separately.
        _dmi(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0,
                                     ec=FakeEC(writable=False))
        assert isinstance(backend, NullFanBackend)
