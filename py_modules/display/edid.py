_BLOCK_SIZE = 128
_CTA_EXTENSION = 0x02
_EXTENDED_DATA_BLOCK = 0x07
_HDR_STATIC_METADATA = 0x06
_EOTF_ST2084 = 1 << 2


def supports_pq(edid):
    if not isinstance(edid, bytes) or len(edid) < _BLOCK_SIZE:
        return False
    if edid[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return False
    block_count = edid[126] + 1
    required = block_count * _BLOCK_SIZE
    if len(edid) < required:
        return False
    blocks = [
        edid[offset:offset + _BLOCK_SIZE]
        for offset in range(0, required, _BLOCK_SIZE)
    ]
    if any(sum(block) & 0xFF for block in blocks):
        return False
    for extension in blocks[1:]:
        if extension[0] != _CTA_EXTENSION:
            continue
        end = extension[2] or 127
        if end < 4 or end > 127:
            return False
        offset = 4
        while offset < end:
            header = extension[offset]
            length = header & 0x1F
            tag = header >> 5
            next_offset = offset + 1 + length
            if next_offset > end:
                return False
            payload = extension[offset + 1:next_offset]
            if (
                tag == _EXTENDED_DATA_BLOCK
                and len(payload) >= 2
                and payload[0] == _HDR_STATIC_METADATA
                and payload[1] & _EOTF_ST2084
            ):
                return True
            offset = next_offset
    return False
