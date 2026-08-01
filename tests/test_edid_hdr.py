from display.edid import supports_pq


def _checksum(block):
    block[-1] = (-sum(block[:-1])) & 0xFF
    return bytes(block)


def _edid(eotf_flags):
    base = bytearray(128)
    base[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    base[126] = 1
    extension = bytearray(128)
    extension[0] = 0x02
    extension[1] = 0x03
    extension[2] = 8
    extension[4:8] = bytes((0xE3, 0x06, eotf_flags, 0x00))
    return _checksum(base) + _checksum(extension)


def test_edid_hdr_static_metadata_advertises_pq():
    assert supports_pq(_edid(0b00000101)) is True


def test_edid_hdr_block_without_st2084_is_not_pq():
    assert supports_pq(_edid(0b00000001)) is False


def test_edid_rejects_truncated_or_bad_checksum_data():
    valid = _edid(0b00000101)
    assert supports_pq(valid[:-1]) is False
    corrupt = bytearray(valid)
    corrupt[130] ^= 0x01
    assert supports_pq(bytes(corrupt)) is False
