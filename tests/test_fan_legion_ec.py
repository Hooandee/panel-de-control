"""Legion Go 2 raw-EC fan backend. The real backend pokes /dev/port; tests inject
a FakeEC (dict-backed) and a synthetic DMI so no hardware is touched. The EC
protocol (registers, 16-bit LE) was confirmed read-only on the real device."""
import os

from fans.legion_ec import (
    LegionGo2FanBackend,
    LegionGoSFanBackend,
    REG_OVERRIDE,
    REG_RPM,
    _GOS_MAX_RPM,
    _GOS_MIN_SPIN,
    _GOS_TEMP_GUARD_C,
)
from fans.control import select_fan_backend, NullFanBackend


class FakeEC:
    def __init__(self):
        self.mem = {}

    def read(self, addr):
        return self.mem.get(addr, 0)

    def write(self, addr, val):
        self.mem[addr] = val & 0xFF


def _dmi(root, version="Legion Go 8ASP2", name="83N0"):
    d = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "product_version"), "w") as f:
        f.write(version)
    with open(os.path.join(d, "product_name"), "w") as f:
        f.write(name)


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _backend(root, ec, temp=70.0):
    return LegionGo2FanBackend(root=str(root), ec=ec, temp_fn=lambda: temp)


class TestLegionBackend:
    def test_supported_when_dmi_matches(self, tmp_path):
        _dmi(str(tmp_path))
        assert _backend(tmp_path, FakeEC()).supported is True

    def test_unsupported_when_dmi_mismatch(self, tmp_path):
        _dmi(str(tmp_path), version="ROG Ally RC71L", name="RC71L")
        assert _backend(tmp_path, FakeEC()).supported is False

    def test_read_rpm_decodes_16bit_le(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        ec.write(REG_RPM, 0x96)       # low  (0x0A96 = 2710)
        ec.write(REG_RPM + 1, 0x0A)   # high
        st = _backend(tmp_path, ec).read_state()
        assert st["fans"][0]["rpm"] == 2710

    def test_apply_writes_override_nonzero(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec, temp=85.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        written = (ec.read(REG_OVERRIDE + 1) << 8) | ec.read(REG_OVERRIDE)
        assert written == b.target_for_temp(85.0)
        assert written > 0

    def test_set_auto_writes_zero_override(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert ec.read(REG_OVERRIDE) == 0
        assert ec.read(REG_OVERRIDE + 1) == 0

    def test_zero_duty_stays_manual_not_release(self, tmp_path):
        # 0% duty at cool temp must drive >=1, NOT write 0 (which = release override).
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec, temp=40.0)  # 40C → CURVE duty 0
        b.apply_curve_all(CURVE)
        written = (ec.read(REG_OVERRIDE + 1) << 8) | ec.read(REG_OVERRIDE)
        assert written >= 1

    def test_target_monotonic_in_range(self, tmp_path):
        _dmi(str(tmp_path))
        b = _backend(tmp_path, FakeEC())
        b.apply_curve_all(CURVE)
        assert 0 <= b.target_for_temp(45) <= b.target_for_temp(90) <= b.max_rpm

    def test_factory_selects_legion_when_dmi_matches(self, tmp_path):
        _dmi(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0)
        assert isinstance(backend, LegionGo2FanBackend)

    def test_factory_null_when_nothing_matches(self, tmp_path):
        _dmi(str(tmp_path), version="ROG Ally", name="RC71L")
        assert isinstance(select_fan_backend(None, root=str(tmp_path)), NullFanBackend)


def _dmi_gos(root, name="83N6", family="Legion Go S 8APU1"):
    d = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(d, exist_ok=True)
    for attr, val in (("product_name", name), ("product_family", family), ("product_version", "")):
        with open(os.path.join(d, attr), "w") as f:
            f.write(val)


class TestLegionGoSBackend:
    def test_supported_when_dmi_matches(self, tmp_path):
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=FakeEC(), temp_fn=lambda: 70.0)
        assert b.supported is True

    def test_not_a_go2(self, tmp_path):
        # A Go S must not be picked up by the Go 2 backend (distinct DMI tokens).
        _dmi_gos(str(tmp_path))
        assert LegionGo2FanBackend(root=str(tmp_path), ec=FakeEC()).supported is False

    def test_experimental_gate_off_gives_null(self, tmp_path):
        _dmi_gos(str(tmp_path))
        assert isinstance(select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0),
                          NullFanBackend)

    def test_experimental_gate_on_selects_gos(self, tmp_path):
        _dmi_gos(str(tmp_path))
        b = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0, experimental=True)
        assert isinstance(b, LegionGoSFanBackend)

    def test_rpm_capped_at_safe_max(self, tmp_path):
        # 100%-duty point must never target above the safety cap.
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=FakeEC(), temp_fn=lambda: 95.0)
        b.apply_curve_all(CURVE)
        assert 0 < b.target_for_temp(95.0) <= _GOS_MAX_RPM

    def test_temp_guardian_forces_max(self, tmp_path):
        # Past the hard limit, ignore the curve and drive the capped max (never undercool).
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=FakeEC(), temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)  # a gentle curve
        assert b.target_for_temp(_GOS_TEMP_GUARD_C) == _GOS_MAX_RPM
        assert b.target_for_temp(_GOS_TEMP_GUARD_C + 10) == _GOS_MAX_RPM

    def test_set_auto_releases(self, tmp_path):
        _dmi_gos(str(tmp_path))
        ec = FakeEC()
        b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert ec.read(REG_OVERRIDE) == 0 and ec.read(REG_OVERRIDE + 1) == 0

    def test_cool_point_releases_not_dead_zone(self, tmp_path):
        # A 0-duty (cool) curve point hands the fan back to firmware (target 0), it
        # does NOT write a sub-spin value that stops the fan while owning it.
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=FakeEC(), temp_fn=lambda: 40.0)
        b.apply_curve_all(CURVE)  # 40C -> duty 0
        assert b.target_for_temp(40.0) == 0

    def test_never_targets_the_dead_zone(self, tmp_path):
        # Across the whole range, every target is either 0 (firmware) or a real
        # spinnable speed in [MIN_SPIN, MAX_RPM] — never the stopped-but-owned zone.
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=FakeEC(), temp_fn=lambda: 60.0)
        b.apply_curve_all(CURVE)
        for temp in range(35, 101):
            t = b.target_for_temp(float(temp))
            assert t == 0 or _GOS_MIN_SPIN <= t <= _GOS_MAX_RPM, f"{temp}C -> {t}"
