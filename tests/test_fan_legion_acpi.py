from fans import legion_acpi as la


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
