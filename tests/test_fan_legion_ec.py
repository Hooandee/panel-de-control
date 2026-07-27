"""Legion Go 2 raw-EC fan backend. The real backend pokes /dev/port; tests inject
a FakeEC (dict-backed) and a synthetic DMI so no hardware is touched. The EC
protocol (registers, 16-bit LE) was confirmed read-only on the real device."""
import os

from fans.legion_ec import (
    LegionGo2FanBackend,
    LegionGoRpmReader,
    LegionGoSFanBackend,
    REG_OVERRIDE,
    REG_RPM,
    REG_RPM_83E1,
    _GOS_MAX_RPM,
    _GOS_MIN_SPIN,
    _GOS_TEMP_GUARD_C,
    select_legion_rpm_reader,
)
from fans.control import select_fan_backend, NullFanBackend


class FakeEC:
    def __init__(self):
        self.mem = {}

    def read(self, addr):
        return self.mem.get(addr, 0)

    def write(self, addr, val):
        self.mem[addr] = val & 0xFF
        return True  # mirror _PortEC.write (True on success)


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


class _WriteFailsEC(FakeEC):
    """EC whose writes always fail (models /dev/port blocked by the OS/kernel:
    os.pwrite raises OSError → _PortEC.write returns False)."""

    def write(self, addr, val):
        return False


class _IgnoresWritesEC(FakeEC):
    """EC whose writes succeed at the syscall level but never move the fan; the
    tachometer stays at idle regardless of the override."""

    def __init__(self, idle_rpm=1889):
        super().__init__()
        self._idle = idle_rpm
        self.mem[REG_RPM] = idle_rpm & 0xFF
        self.mem[REG_RPM + 1] = (idle_rpm >> 8) & 0xFF

    def write(self, addr, val):
        # The override register takes the write (readback matches), but the fan is
        # unmoved — the tachometer stays pinned at idle.
        ok = super().write(addr, val)
        if addr in (REG_OVERRIDE, REG_OVERRIDE + 1):
            self.mem[REG_RPM] = self._idle & 0xFF
            self.mem[REG_RPM + 1] = (self._idle >> 8) & 0xFF
        return ok


class _ReflectingEC(FakeEC):
    """Working EC: the override we write becomes the reported RPM (the fan obeys)."""

    def write(self, addr, val):
        super().write(addr, val)
        if addr == REG_OVERRIDE:
            self.mem[REG_RPM] = val & 0xFF
        elif addr == REG_OVERRIDE + 1:
            self.mem[REG_RPM + 1] = val & 0xFF
        return True


class TestLegionGoSEcAccessHonesty:
    """Control is confirmed against the tachometer, not the syscall. The backend stays
    DMI-supported but reports manual (enable=1) only when the RPM tracks the asserted
    target."""

    def test_syscall_write_but_ignored_is_not_reported_as_manual(self, tmp_path):
        # Writes return ok at the syscall level, but the fan ignores them.
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=_IgnoresWritesEC(), temp_fn=lambda: 70.0)
        assert b.supported is True  # DMI channel still present
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True  # the write "landed" at the syscall level
        b._apply_once()  # a settled tick confirms against the RPM (still idle → off)
        assert b.read_state()["fans"][0]["enable"] == 2  # honest: firmware, not manual

    def test_blocked_ec_write_not_reported_as_manual(self, tmp_path):
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=_WriteFailsEC(), temp_fn=lambda: 70.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is False  # the write did not even land
        assert b.read_state()["fans"][0]["enable"] == 2

    def test_confirmed_control_reports_manual(self, tmp_path):
        # A working EC: RPM tracks the target → read_state reports manual.
        _dmi_gos(str(tmp_path))
        b = LegionGoSFanBackend(root=str(tmp_path), ec=_ReflectingEC(), temp_fn=lambda: 70.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        assert b.read_state()["fans"][0]["enable"] == 2  # not yet confirmed
        b._apply_once()  # settled tick: RPM now equals the asserted target → confirmed
        assert b.read_state()["fans"][0]["enable"] == 1


class _UnzeroableEC(FakeEC):
    """Accepts override writes at the syscall level (returns ok) but refuses to
    store the release sentinel 0 — models an EC that won't take a release, so a
    readback never confirms the override reached 0."""

    def write(self, addr, val):
        if addr in (REG_OVERRIDE, REG_OVERRIDE + 1) and (val & 0xFF) == 0:
            return True  # syscall ok, register keeps its prior (nonzero) value
        return super().write(addr, val)


class _HighByteFailsEC(FakeEC):
    """The override high byte can never be written (a flaky EC data channel)."""

    def write(self, addr, val):
        if addr == REG_OVERRIDE + 1:
            return False
        return super().write(addr, val)


class _LowByteFailsEC(FakeEC):
    """The override low byte can never be written."""

    def write(self, addr, val):
        if addr == REG_OVERRIDE:
            return False
        return super().write(addr, val)


class TestReleaseReadbackAndDeadZone:
    """Release is confirmed by reading the override back (a write returning ok is
    not proof the EC took it), and a fan is never abandoned in the stopped-but-
    owned dead zone when release can't be confirmed."""

    def test_release_confirmed_reports_ok_and_zeroes_override(self, tmp_path):
        _dmi_gos(str(tmp_path))
        ec = FakeEC()
        b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)
        res = b.set_auto(None)
        assert res["ok"] is True
        assert ec.read(REG_OVERRIDE) == 0 and ec.read(REG_OVERRIDE + 1) == 0

    def test_release_unconfirmed_keeps_fan_out_of_dead_zone(self, tmp_path):
        # The EC won't accept 0, so release can't be confirmed. The backend must
        # report failure AND leave a safe spinning target, never a value in the
        # stopped-but-owned dead zone (0, MIN_SPIN).
        _dmi_gos(str(tmp_path))
        ec = _UnzeroableEC()
        b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)  # drives a positive override
        res = b.set_auto(None)
        assert res["ok"] is False  # readback never confirmed release
        final = (ec.read(REG_OVERRIDE + 1) << 8) | ec.read(REG_OVERRIDE)
        assert final >= _GOS_MIN_SPIN

    def test_go2_release_confirms_via_readback(self, tmp_path):
        _dmi(str(tmp_path))
        ec = FakeEC()
        b = _backend(tmp_path, ec, temp=70.0)
        b.apply_curve_all(CURVE)
        assert b.set_auto(None)["ok"] is True
        assert ec.read(REG_OVERRIDE) == 0 and ec.read(REG_OVERRIDE + 1) == 0

    def _ovr(self, ec):
        return (ec.read(REG_OVERRIDE + 1) << 8) | ec.read(REG_OVERRIDE)

    def test_split_write_high_byte_failure_never_strands_dead_zone(self, tmp_path):
        # The override high byte can never land: a driven target must not leave a
        # partial low-only value in the (0, MIN_SPIN) dead zone.
        _dmi_gos(str(tmp_path))
        ec = _HighByteFailsEC()
        b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)
        assert self._ovr(ec) == 0 or self._ovr(ec) >= _GOS_MIN_SPIN
        b.set_auto(None)
        assert self._ovr(ec) == 0 or self._ovr(ec) >= _GOS_MIN_SPIN

    def test_split_write_low_byte_failure_never_strands_dead_zone(self, tmp_path):
        # The override low byte can never land: high-first leaves high<<8 >= MIN_SPIN.
        _dmi_gos(str(tmp_path))
        ec = _LowByteFailsEC()
        b = LegionGoSFanBackend(root=str(tmp_path), ec=ec, temp_fn=lambda: 70.0)
        b.apply_curve_all(CURVE)
        assert self._ovr(ec) == 0 or self._ovr(ec) >= _GOS_MIN_SPIN
        b.set_auto(None)
        assert self._ovr(ec) == 0 or self._ovr(ec) >= _GOS_MIN_SPIN

    def test_cool_curve_point_reports_firmware_not_stale_manual(self, tmp_path):
        # Confirmed driving at 70C, then cool to 40C where the curve commands 0
        # (firmware). read_state must report firmware(2), not a stale manual(1).
        _dmi_gos(str(tmp_path))
        temp = {"v": 70.0}
        b = LegionGoSFanBackend(root=str(tmp_path), ec=_ReflectingEC(), temp_fn=lambda: temp["v"])
        b.apply_curve_all(CURVE)
        b._apply_once()  # settled tick: RPM tracks target → manual
        assert b.read_state()["fans"][0]["enable"] == 1
        temp["v"] = 40.0  # curve maps to 0 → hand to firmware
        b._apply_once()
        assert b.read_state()["fans"][0]["enable"] == 2


class TestLegionGo1RpmReader:
    def test_decodes_16bit_le(self):
        ec = FakeEC()
        ec.mem[REG_RPM_83E1] = 0xCC       # 204
        ec.mem[REG_RPM_83E1 + 1] = 0x0C   # 12 -> (12<<8)|204 = 3276
        assert LegionGoRpmReader(ec=ec).read_rpm() == 3276

    def test_none_when_read_fails(self):
        class DeadEC:
            def read(self, addr):
                return None
        assert LegionGoRpmReader(ec=DeadEC()).read_rpm() is None

    def test_selector_only_for_legion_go(self):
        from device_profiles import DEVICE_TABLE
        legion = next(d for d in DEVICE_TABLE if d.key == "legion_go")
        go2 = next(d for d in DEVICE_TABLE if d.key == "legion_go_2")
        assert select_legion_rpm_reader(legion, ec=FakeEC()) is not None
        assert select_legion_rpm_reader(go2, ec=FakeEC()) is None
