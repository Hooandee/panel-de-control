import os

from fans import legion_acpi as la
from fans.legion_acpi import LegionAcpiCallFanBackend


def test_encode_set_curve_layout():
    speeds = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    arg = la.encode_set_curve(speeds)
    assert arg.startswith("b")
    raw = bytes.fromhex(arg[1:])
    assert len(raw) == 52
    assert raw[0:6] == bytes([0x00, 0x00, 0x0A, 0x00, 0x00, 0x00])   # header, u16@2 = 10
    assert [raw[6 + 2 * i] for i in range(10)] == speeds             # 10 speeds, u16 LE
    assert raw[26:31] == bytes([0x00, 0x0A, 0x00, 0x00, 0x00])       # temp sub-header
    assert [raw[31 + 2 * i] for i in range(10)] == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert raw[51] == 0x00                                            # trailing pad


def test_encode_get_curve():
    assert la.encode_get_curve() == "b00000000"


def test_decode_get_curve_stride_4():
    vals = list(range(41))
    resp = "{" + ", ".join(hex(v) for v in vals) + "}"
    assert la.decode_get_curve(resp) == [4, 8, 12, 16, 20, 24, 28, 32, 36, 40]


def test_decode_get_curve_rejects_short_or_junk():
    assert la.decode_get_curve("not called") is None
    assert la.decode_get_curve("{0x1, 0x2}") is None
    assert la.decode_get_curve(None) is None


def test_encode_set_max_on_off():
    assert la.encode_set_max(True) == "b0000020401000000"
    assert la.encode_set_max(False) == "b0000020400000000"


def test_clamp_floor_raises_each_point_to_min_curve():
    assert la.clamp_floor([0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) == la.MIN_CURVE
    assert la.clamp_floor([100] * 10) == [100] * 10
    assert la.clamp_floor([50, 10, 60, 10, 80, 10, 90, 10, 100, 10]) == \
        [50, 48, 60, 60, 80, 79, 90, 87, 100, 100]


def test_curve_to_speeds_resamples_and_floors():
    assert la.curve_to_speeds([(0, 0), (100, 0)]) == la.MIN_CURVE
    assert la.curve_to_speeds([(0, 255), (100, 255)]) == [100] * 10


class FakeGzfd:
    """Simulates \\_SB.GZFD over acpi_call: remembers the last SET curve and echoes it
    back on GET in the stride-4 wire layout; records full-speed writes."""

    def __init__(self):
        self.speeds = [40] * 10   # firmware "stock" curve
        self.max_on = False
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        if ".WMAB 0x00 0x06 " in command:
            arg = command.rsplit(" ", 1)[-1]
            raw = bytes.fromhex(arg[1:])
            self.speeds = [raw[6 + 2 * i] for i in range(10)]
            return "0x0"
        if ".WMAB 0x00 0x05 " in command:
            b = [0] * 44
            for i in range(10):
                b[4 + 4 * i] = self.speeds[i]
            return "{" + ", ".join(hex(v) for v in b[:41]) + "}"
        if ".WMAE 0x00 0x12 " in command:
            self.max_on = command.rstrip().endswith("01000000")
            return "0x0"
        return "0x0"


def _writable_node(root):
    d = os.path.join(root, "proc/acpi")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "call")
    with open(p, "w") as f:
        f.write("not called")
    return p


def _mk_backend(tmp_path):
    _writable_node(tmp_path)
    fake = FakeGzfd()
    b = LegionAcpiCallFanBackend(root=str(tmp_path), caller=fake, modprobe=lambda m: None)
    return b, fake


def test_supported_when_acpi_call_available(tmp_path):
    b, _ = _mk_backend(tmp_path)
    assert b.supported is True
    assert b.supports_max is True


def test_unsupported_when_no_acpi_call(tmp_path):
    fake = FakeGzfd()
    b = LegionAcpiCallFanBackend(root=str(tmp_path), caller=fake, modprobe=lambda m: None)
    assert b.supported is False


def test_set_curve_writes_floored_curve_and_readback_confirms(tmp_path):
    b, fake = _mk_backend(tmp_path)
    res = b.set_curve("fan", [(0, 0), (100, 255)])
    assert res["ok"] is True
    assert fake.speeds[-1] == 100
    assert all(fake.speeds[i] >= la.MIN_CURVE[i] for i in range(10))


def test_set_curve_fails_when_readback_mismatches(tmp_path):
    b, fake = _mk_backend(tmp_path)

    def liar(command):
        if ".WMAB 0x00 0x05 " in command:
            return "{" + ", ".join(["0x0"] * 41) + "}"
        return fake(command)

    b._call = liar
    res = b.set_curve("fan", [(50, 255)])
    assert res["ok"] is False
    assert "readback" in res["detail"]


def test_apply_curve_all_is_single_fan(tmp_path):
    b, fake = _mk_backend(tmp_path)
    assert b.apply_curve_all([(0, 128), (100, 255)])["ok"] is True


def test_set_max_on_then_off(tmp_path):
    b, fake = _mk_backend(tmp_path)
    assert b.set_max(True)["ok"] is True
    assert fake.max_on is True
    assert b.set_max(False)["ok"] is True
    assert fake.max_on is False


def test_read_state_after_prime_reports_curve(tmp_path):
    b, fake = _mk_backend(tmp_path)
    b.prime()
    st = b.read_state()
    assert st["supported"] is True
    assert st["fans"] and len(st["fans"][0]["points"]) == 10


def test_restore_auto_writes_raw_stock_curve_and_clears_max(tmp_path):
    b, fake = _mk_backend(tmp_path)
    b.prime()                       # captures stock [40]*10
    b.set_max(True)
    b.set_curve("fan", [(50, 255)])
    assert b.restore_auto()["ok"] is True
    assert fake.max_on is False
    # Restores the stock curve verbatim — NOT re-floored to MIN_CURVE (which would
    # leave the idle fan louder than the firmware baseline).
    assert fake.speeds == [40] * 10


def test_set_auto_is_noop_curve_when_never_drove(tmp_path):
    # We never wrote a manual curve: 'auto' must not touch the curve at all (writing
    # MIN_CURVE here would floor the idle fan above stock). Only max is cleared.
    b, fake = _mk_backend(tmp_path)
    b.prime()
    fake.commands.clear()
    assert b.set_auto()["ok"] is True
    assert fake.speeds == [40] * 10                      # untouched
    assert not any(".WMAB 0x00 0x06 " in c for c in fake.commands)   # no curve write
