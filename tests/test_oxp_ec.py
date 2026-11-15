import pytest

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

FLOOR = oxp_ec._APEX_DUTY_FLOOR
ALLY = {"board": "ROG Ally RC71L", "product": "ROG Ally RC71L"}


class FakeEC:
    def __init__(self, mem=None, writable=True, refuse=(), lose_readback=None):
        self.mem = dict(mem or {})
        self._writable = writable
        self._refuse = refuse
        self._lose_readback = lose_readback
        self.writable_calls = 0
        self.writes = []

    def read(self, addr):
        if addr == REG_MODE and self._lose_readback is not None and self.mem.get(addr) == self._lose_readback:
            return None
        return self.mem.get(addr)

    def write(self, addr, val):
        if not self._writable or (addr, val) in self._refuse or (addr, None) in self._refuse:
            return False
        self.mem[addr] = val & 0xFF
        self.writes.append((addr, val & 0xFF))
        return True

    def writable(self):
        self.writable_calls += 1
        return self._writable


def _apex_root(tmp_path, board="ONEXPLAYER APEX", product="ONEXPLAYER APEX",
               vendor="ONE-NETBOOK"):
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "board_name").write_text(board + "\n")
    (dmi / "product_name").write_text(product + "\n")
    (dmi / "board_vendor").write_text(vendor + "\n")
    return str(tmp_path)


def _hwmon(tmp_path, name, leaf):
    chip = tmp_path / "sys/class/hwmon/hwmon5"
    chip.mkdir(parents=True)
    (chip / "name").write_text(name + "\n")
    (chip / leaf).write_text("128\n")


def _make(tmp_path, ec=None, **kw):
    return OxpEcFanBackend(root=_apex_root(tmp_path, **kw), ec=ec or FakeEC())


def test_apex_is_eligible_without_probing_ec_until_state_is_read(tmp_path):
    ec = FakeEC()
    b = _make(tmp_path, ec=ec)
    assert b.eligible is True and b.supported is False
    assert ec.writable_calls == 0
    assert b.read_state()["supported"] is True
    assert b.supported is True
    assert ec.writable_calls == 1


def test_read_state_is_unsupported_when_ec_is_not_writable(tmp_path):
    st = _make(tmp_path, ec=FakeEC(writable=False)).read_state()
    assert st["supported"] is False
    assert st["fans"] == []


@pytest.mark.parametrize("dmi", [
    pytest.param(ALLY, id="other-machine"),
    pytest.param({"board": "OTHER BOARD"}, id="product-name-alone"),
    pytest.param({"vendor": "OTHER VENDOR"}, id="wrong-board-vendor"),
])
def test_raw_ec_stays_off_outside_the_exact_apex_dmi(tmp_path, dmi):
    b = _make(tmp_path, **dmi)
    b.read_state()
    assert b.supported is False


def test_hands_off_when_oxp_hwmon_fan_node_present(tmp_path):
    _hwmon(tmp_path, "oxp_ec", "pwm1")
    b = _make(tmp_path)
    b.read_state()
    assert b.supported is False


@pytest.mark.parametrize("name,leaf,present", [
    ("oxp_ec", "fan1_input", True),
    ("amdgpu", "fan1_input", False),
])
def test_oxpec_hwmon_presence(tmp_path, name, leaf, present):
    _hwmon(tmp_path, name, leaf)
    assert oxp_ec.oxpec_hwmon_present(str(tmp_path)) is present


def test_write_target_sets_duty_before_manual(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO})
    assert _make(tmp_path, ec=ec)._write_target(180) is True
    assert ec.writes[:2] == [(REG_DUTY, 180), (REG_MODE, MODE_MANUAL)]


@pytest.mark.parametrize("asked,written", [(999, 255), (0, FLOOR)])
def test_write_target_clamps_duty(tmp_path, asked, written):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO})
    assert _make(tmp_path, ec=ec)._write_target(asked) is True
    assert ec.mem[REG_DUTY] == written


@pytest.mark.parametrize("ec", [
    pytest.param(FakeEC(mem={REG_MODE: MODE_AUTO, REG_DUTY: 120}, refuse=((REG_DUTY, None),)),
                 id="duty-write-refused"),
    pytest.param(FakeEC(mem={REG_MODE: MODE_AUTO, REG_DUTY: 120}, lose_readback=MODE_MANUAL),
                 id="manual-readback-lost"),
    pytest.param(FakeEC(mem={REG_MODE: MODE_AUTO}, writable=False), id="ec-not-writable"),
])
def test_failed_write_target_never_leaves_the_fan_in_manual(tmp_path, ec):
    assert _make(tmp_path, ec=ec)._write_target(180) is False
    assert ec.mem[REG_MODE] == MODE_AUTO


def test_release_sets_auto_confirmed(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_MANUAL, REG_DUTY: 200})
    assert _make(tmp_path, ec=ec)._release() is True
    assert ec.mem[REG_MODE] == MODE_AUTO


@pytest.mark.parametrize("ec,mode,duty", [
    pytest.param(FakeEC(mem={REG_MODE: MODE_MANUAL, REG_DUTY: 90}, writable=False),
                 MODE_MANUAL, 90, id="ec-not-writable"),
    pytest.param(FakeEC(mem={REG_MODE: MODE_MANUAL, REG_DUTY: FLOOR}, refuse=((REG_MODE, MODE_AUTO),)),
                 MODE_MANUAL, 255, id="auto-refused-leaves-full-duty"),
    pytest.param(FakeEC(mem={REG_MODE: MODE_MANUAL, REG_DUTY: 120}, refuse=((REG_DUTY, 255),),
                        lose_readback=MODE_AUTO),
                 MODE_AUTO, 120, id="no-manual-reentry-without-confirmed-full-duty"),
])
def test_failed_release(tmp_path, ec, mode, duty):
    assert _make(tmp_path, ec=ec)._release() is False
    assert (ec.mem[REG_MODE], ec.mem[REG_DUTY]) == (mode, duty)


@pytest.mark.parametrize("mem,enable,rpm", [
    pytest.param({REG_MODE: MODE_MANUAL, REG_RPM: 0x0F, REG_RPM + 1: 0xA0}, 1, 0x0FA0, id="manual-big-endian-rpm"),
    pytest.param({REG_MODE: MODE_AUTO, REG_RPM: 0x12}, 2, None, id="auto-rpm-unreadable"),
])
def test_read_state_reports_hardware_mode_and_rpm(tmp_path, mem, enable, rpm):
    fan = _make(tmp_path, ec=FakeEC(mem=mem)).read_state()["fans"][0]
    assert (fan["enable"], fan["rpm"]) == (enable, rpm)


@pytest.mark.parametrize("points,temp,duty", [
    pytest.param([[40, 0], [60, 100], [80, 200], [90, 255]], 70, 150, id="duty-identity-interpolated"),
    pytest.param([[40, 0], [60, 40], [80, 60]], 95, 255, id="hot-guardian-forces-full"),
    pytest.param([[40, 0], [70, 30], [90, 255]], 40, FLOOR, id="cool-point-clamped-to-floor"),
    pytest.param(None, 70, None, id="no-points"),
])
def test_target_for_temp(tmp_path, points, temp, duty):
    b = _make(tmp_path)
    b._points = points
    assert b.target_for_temp(temp) == duty


def test_missing_temperature_releases_to_firmware(tmp_path):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO, REG_DUTY: 120})
    b = _make(tmp_path, ec=ec)
    b._temp_fn = lambda: None
    assert b.apply_curve_all([[40, 0], [90, 255]])["ok"] is False
    assert ec.mem[REG_MODE] == MODE_AUTO


@pytest.mark.parametrize("writable", [True, False])
def test_before_drive_follows_ec_writability(tmp_path, writable):
    ec = FakeEC(mem={REG_MODE: MODE_AUTO}, writable=writable)
    assert _make(tmp_path, ec=ec)._before_drive() is writable


@pytest.mark.parametrize("dmi,experimental,selected", [
    pytest.param({}, True, OxpEcFanBackend, id="apex-opted-in"),
    pytest.param({}, False, NullFanBackend, id="apex-opt-in-off"),
    pytest.param(ALLY, True, NullFanBackend, id="other-machine-opted-in"),
])
def test_factory_selects_apex_only_when_opted_in(tmp_path, dmi, experimental, selected):
    root = _apex_root(tmp_path, **dmi)
    b = select_fan_backend(None, root=root, temp_fn=lambda: 60.0, experimental=experimental)
    assert type(b) is selected
