from fans import oxp_ec
from fans.control import NullFanBackend, select_fan_backend
from fans.oxp_ec import (
    MODE_AUTO,
    MODE_MANUAL,
    REG_DUTY,
    REG_MODE,
    REG_RPM,
    OxpEcFanBackend,
)


class FakeEC:
    """In-memory EC for tests — no debugfs, no hardware. `writable=False` models a
    kernel where ec_sys has no write support (pwrite fails)."""

    def __init__(self, mem=None, writable=True):
        self.mem = dict(mem or {})
        self._writable = writable
        self.writes = []
        self.reads = []

    def read(self, addr):
        self.reads.append(addr)
        return self.mem.get(addr)

    def write(self, addr, val):
        if not self._writable:
            return False
        self.mem[addr] = val & 0xFF
        self.writes.append((addr, val & 0xFF))
        return True

    def writable(self):
        return self._writable


def _apex_root(tmp_path, board="ONEXPLAYER APEX", product="ONEXPLAYER APEX"):
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "board_name").write_text(board + "\n")
    (dmi / "product_name").write_text(product + "\n")
    (dmi / "board_vendor").write_text("ONE-NETBOOK\n")
    return str(tmp_path)


def _make(tmp_path, ec=None, **kw):
    root = _apex_root(tmp_path, **kw)
    return OxpEcFanBackend(root=root, ec=ec or FakeEC())


# --- detection / handoff ----------------------------------------------------

def test_supported_on_apex_dmi(tmp_path):
    assert _make(tmp_path).supported is True


def test_not_supported_off_apex_dmi(tmp_path):
    b = OxpEcFanBackend(root=_apex_root(tmp_path, board="ROG Ally RC71L", product="ROG Ally RC71L"),
                        ec=FakeEC())
    assert b.supported is False


def test_hands_off_when_oxp_hwmon_fan_node_present(tmp_path):
    # A future kernel ships the oxpec hwmon driver → the generic pwm path takes over,
    # so this raw-EC backend must bow out (vía-1 → vía-2 handoff).
    root = _apex_root(tmp_path)
    chip = tmp_path / "sys/class/hwmon/hwmon5"
    chip.mkdir(parents=True)
    (chip / "name").write_text("oxp_ec\n")
    (chip / "pwm1").write_text("128\n")
    assert OxpEcFanBackend(root=root, ec=FakeEC()).supported is False


# --- driving (duty + mode), confirmed by readback ---------------------------

def test_write_target_sets_manual_then_duty_confirmed(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO})
    b = _make(tmp_path, ec=ec)
    assert b._write_target(180) is True
    # manual mode asserted before the duty write
    assert ec.writes[0] == (REG_MODE, MODE_MANUAL)
    assert (REG_DUTY, 180) in ec.writes
    assert ec.mem[REG_MODE] == MODE_MANUAL and ec.mem[REG_DUTY] == 180


def test_write_target_clamps_duty_to_255(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_MANUAL})
    b = _make(tmp_path, ec=ec)
    b._write_target(999)
    assert ec.mem[REG_DUTY] == 255


def test_write_target_fails_when_not_writable(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO}, writable=False)
    b = _make(tmp_path, ec=ec)
    assert b._write_target(120) is False


def test_release_sets_auto_confirmed(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_MANUAL, REG_DUTY: 200})
    b = _make(tmp_path, ec=ec)
    assert b._release() is True
    assert ec.mem[REG_MODE] == MODE_AUTO


def test_release_false_when_write_refused(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_MANUAL}, writable=False)
    b = _make(tmp_path, ec=ec)
    assert b._release() is False


# --- RPM read (big-endian) --------------------------------------------------

def test_read_rpm_big_endian(tmp_path):
    ec = FakeEC(mem={REG_RPM: 0x12, REG_RPM + 1: 0x34})
    b = _make(tmp_path, ec=ec)
    assert b._read_rpm() == 0x1234


def test_read_rpm_none_when_unreadable(tmp_path):
    ec = FakeEC(mem={REG_RPM: 0x12})  # low byte missing
    b = _make(tmp_path, ec=ec)
    assert b._read_rpm() is None


# --- curve → duty (identity, temp guardian) ---------------------------------

def test_target_for_temp_is_duty_identity(tmp_path):
    b = _make(tmp_path)
    b._points = [[40, 0], [60, 100], [80, 200], [90, 255]]
    # 70 °C interpolates between (60,100) and (80,200) → 150 duty
    assert b.target_for_temp(70) == 150


def test_target_for_temp_guardian_forces_full_when_hot(tmp_path):
    b = _make(tmp_path)
    b._points = [[40, 0], [60, 40], [80, 60]]  # a lazy curve
    assert b.target_for_temp(95) == 255  # guardian overrides


def test_target_for_temp_none_without_points_or_temp(tmp_path):
    b = _make(tmp_path)
    assert b.target_for_temp(70) is None
    b._points = [[40, 0], [90, 255]]
    assert b.target_for_temp(None) is None


# --- read_state reports the true hardware mode ------------------------------

def test_read_state_manual_from_mode_register(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_MANUAL, REG_RPM: 0x0F, REG_RPM + 1: 0xA0})
    b = _make(tmp_path, ec=ec)
    st = b.read_state()
    assert st["supported"] is True
    assert st["fans"][0]["enable"] == 1
    assert st["fans"][0]["rpm"] == 0x0FA0


def test_read_state_auto_from_mode_register(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO})
    b = _make(tmp_path, ec=ec)
    assert b.read_state()["fans"][0]["enable"] == 2


# --- before_drive writability probe -----------------------------------------

def test_before_drive_true_when_ec_writable(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO})
    b = _make(tmp_path, ec=ec)
    assert b._before_drive() is True  # root != "/" so no modprobe; probe uses FakeEC


def test_before_drive_false_when_ec_not_writable(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO}, writable=False)
    b = _make(tmp_path, ec=ec)
    assert b._before_drive() is False


# --- factory selection (opt-in gate) ----------------------------------------

def test_factory_selects_apex_when_experimental_on(tmp_path):
    root = _apex_root(tmp_path)
    b = select_fan_backend(None, root=root, temp_fn=lambda: 60.0, experimental=True)
    assert isinstance(b, OxpEcFanBackend)


def test_factory_apex_not_selected_when_experimental_off(tmp_path):
    # Opt-in: with the toggle off the Apex falls through to the read-only monitor.
    root = _apex_root(tmp_path)
    b = select_fan_backend(None, root=root, temp_fn=lambda: 60.0, experimental=False)
    assert isinstance(b, NullFanBackend)


def test_factory_does_not_select_apex_on_other_machine(tmp_path):
    # A non-Apex handheld must never get the Apex backend, even with the toggle on.
    root = _apex_root(tmp_path, board="ROG Ally RC71L", product="ROG Ally RC71L")
    b = select_fan_backend(None, root=root, temp_fn=lambda: 60.0, experimental=True)
    assert not isinstance(b, OxpEcFanBackend)


# --- oxpec hwmon presence (drives the kernel-pending UI note) ---------------

def test_oxpec_hwmon_present_true_with_pwm_node(tmp_path):
    chip = tmp_path / "sys/class/hwmon/hwmon3"
    chip.mkdir(parents=True)
    (chip / "name").write_text("oxp_ec\n")
    (chip / "fan1_input").write_text("2600\n")
    assert oxp_ec.oxpec_hwmon_present(str(tmp_path)) is True


def test_oxpec_hwmon_present_false_when_absent(tmp_path):
    chip = tmp_path / "sys/class/hwmon/hwmon3"
    chip.mkdir(parents=True)
    (chip / "name").write_text("amdgpu\n")
    assert oxp_ec.oxpec_hwmon_present(str(tmp_path)) is False
