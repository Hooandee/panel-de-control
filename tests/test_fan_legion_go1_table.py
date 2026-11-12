"""Legion Go original (83E1) fan table backend with an injected EC window."""
import os

from fans.control import select_fan_backend
from fans.legion_ec import (
    GO1_HOT_FLOOR,
    GO1_RPM,
    GO1_SFNT,
    GO1_STEPS,
    GO1_TABLE,
    LegionGoFanTableBackend,
)

FIRMWARE_TABLE = [44, 48, 55, 60, 71, 79, 87, 87, 100, 0]


class FakeMem:
    def __init__(self, ok=True):
        self.mem = {GO1_SFNT: 0}
        for i, v in enumerate(FIRMWARE_TABLE):
            self.mem[GO1_TABLE + i] = v
        self.ok = ok
        self.writes = []
        self.ignore = set()

    def available(self):
        return self.ok

    def read(self, off):
        return self.mem.get(off, 0) if self.ok else None

    def write(self, off, val):
        self.writes.append((off, val))
        if off not in self.ignore:
            self.mem[off] = val & 0xFF
        return self.ok

    def table(self):
        return [self.mem[GO1_TABLE + i] for i in range(GO1_STEPS)]


def _dmi(root, name="83E1", version="Legion Go 8APU1"):
    d = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "product_name"), "w") as f:
        f.write(name)
    with open(os.path.join(d, "product_version"), "w") as f:
        f.write(version)


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


class Temp:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def _backend(tmp_path, mem, temp=70.0):
    return LegionGoFanTableBackend(root=str(tmp_path), ec=mem, temp_fn=Temp(temp))


def test_supported_only_on_83e1(tmp_path):
    _dmi(str(tmp_path))
    assert _backend(tmp_path, FakeMem()).supported is True
    _dmi(str(tmp_path), name="83L3", version="Legion Go S 8APU1")
    assert _backend(tmp_path, FakeMem()).supported is False


def test_unsupported_when_the_ec_window_cannot_be_mapped(tmp_path):
    _dmi(str(tmp_path))
    assert _backend(tmp_path, FakeMem(ok=False)).supported is False


def test_apply_writes_the_duty_for_the_apu_temperature(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    result = _backend(tmp_path, mem, temp=70.0).apply_curve_all(CURVE)
    assert result["ok"] is True
    assert mem.mem[GO1_SFNT] == 1
    duty = round(95 * 100 / 255)
    assert mem.table() == LegionGoFanTableBackend.table_for(duty)
    assert mem.table()[:5] == [duty] * 5


def test_custom_mode_is_enabled_only_after_the_table(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    _backend(tmp_path, mem).apply_curve_all(CURVE)
    assert mem.writes[-1] == (GO1_SFNT, 1)
    assert all(off != GO1_SFNT for off, _ in mem.writes[:-1])


def test_hot_steps_keep_the_firmware_minimums(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    _backend(tmp_path, mem, temp=45.0).apply_curve_all(CURVE)
    table = mem.table()
    for value, floor in zip(table, GO1_HOT_FLOOR):
        if floor is not None:
            assert value >= floor
    assert table[0] == round(15 * 100 / 255)


def test_full_speed_past_the_temperature_guard(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    _backend(tmp_path, mem, temp=92.0).apply_curve_all([(40, 0), (100, 10)])
    assert mem.table() == [100] * GO1_STEPS


def test_duty_follows_the_temperature(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    temp = Temp(50.0)
    backend = LegionGoFanTableBackend(root=str(tmp_path), ec=mem, temp_fn=temp)
    backend.apply_curve_all(CURVE)
    cool = mem.table()[0]
    temp.value = 80.0
    assert backend._apply_once() is True
    assert mem.table()[0] > cool
    assert backend.diagnostics()["reasserts"] == 0


def test_release_hands_back_to_firmware(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    backend = _backend(tmp_path, mem)
    backend.apply_curve_all(CURVE)
    assert backend.set_auto(None)["ok"] is True
    assert mem.mem[GO1_SFNT] == 0
    assert backend.read_state()["fans"][0]["enable"] == 2


def test_release_reports_failure_when_firmware_keeps_custom_mode(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    backend = _backend(tmp_path, mem)
    backend.apply_curve_all(CURVE)
    mem.ignore.add(GO1_SFNT)
    assert backend.set_auto(None)["ok"] is False


def test_reasserts_after_firmware_resets_custom_mode(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    backend = _backend(tmp_path, mem)
    backend.apply_curve_all(CURVE)
    mem.mem[GO1_SFNT] = 0
    assert backend._apply_once() is True
    assert mem.mem[GO1_SFNT] == 1
    assert backend.diagnostics()["reasserts"] == 1


def test_steady_state_tick_writes_nothing(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    backend = _backend(tmp_path, mem)
    backend.apply_curve_all(CURVE)
    before = len(mem.writes)
    assert backend._apply_once() is True
    assert len(mem.writes) == before


def test_read_state_reports_rpm_and_manual_mode(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    mem.mem[GO1_RPM] = 0x0C
    mem.mem[GO1_RPM + 1] = 0x16
    backend = _backend(tmp_path, mem)
    backend.apply_curve_all(CURVE)
    fan = backend.read_state()["fans"][0]
    assert fan["rpm"] == 5644
    assert fan["enable"] == 1


def test_failed_readback_is_not_manual(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    mem.ignore.add(GO1_TABLE + 3)
    backend = _backend(tmp_path, mem)
    assert backend.apply_curve_all(CURVE)["ok"] is False
    assert backend.read_state()["fans"][0]["enable"] == 2


class Go1:
    key = "legion_go"


def test_factory_picks_the_table_backend_on_83e1(tmp_path, monkeypatch):
    import fans.legion_ec as legion_ec

    _dmi(str(tmp_path))
    monkeypatch.setattr(legion_ec, "_MemEC", lambda *a, **k: FakeMem())
    backend = select_fan_backend(Go1(), root=str(tmp_path))
    assert isinstance(backend, LegionGoFanTableBackend)


def test_factory_skips_it_on_other_legions(tmp_path, monkeypatch):
    import fans.legion_ec as legion_ec

    _dmi(str(tmp_path), name="83L3", version="Legion Go S 8APU1")
    monkeypatch.setattr(legion_ec, "_MemEC", lambda *a, **k: FakeMem())
    backend = select_fan_backend(type("D", (), {"key": "legion_go_s"})(), root=str(tmp_path))
    assert not isinstance(backend, LegionGoFanTableBackend)


def test_unreadable_temperature_runs_full_speed(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    _backend(tmp_path, mem, temp=None).apply_curve_all(CURVE)
    assert mem.table() == [100] * GO1_STEPS


def test_auto_leaves_another_tools_table_alone(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    mem.mem[GO1_SFNT] = 1
    backend = _backend(tmp_path, mem)
    assert backend.set_auto(None)["ok"] is True
    assert mem.mem[GO1_SFNT] == 1
    assert mem.writes == []


def test_auto_releases_a_table_left_by_a_previous_run(tmp_path):
    _dmi(str(tmp_path))
    mem = FakeMem()
    for i, v in enumerate(LegionGoFanTableBackend.table_for(30)):
        mem.mem[GO1_TABLE + i] = v
    mem.mem[GO1_SFNT] = 1
    assert _backend(tmp_path, mem).set_auto(None)["ok"] is True
    assert mem.mem[GO1_SFNT] == 0


def test_real_ec_is_never_opened_under_a_test_root(tmp_path):
    _dmi(str(tmp_path))
    backend = LegionGoFanTableBackend(root=str(tmp_path))
    assert backend.supported is False


def test_mem_window_maps_per_access(tmp_path):
    import mmap

    from fans.legion_ec import _MemEC

    page = mmap.ALLOCATIONGRANULARITY
    dev = tmp_path / "mem"
    dev.write_bytes(bytes(2 * page))
    ec = _MemEC(str(dev), base=page, size=page)
    assert ec.available() is True
    assert ec.write(0x30E, 1) is True
    assert ec.read(0x30E) == 1
    assert dev.read_bytes()[page + 0x30E] == 1
    assert _MemEC(str(tmp_path / "missing")).available() is False
