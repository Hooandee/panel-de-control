"""Minimal GIF89a decoder for tests: returns composited index frames and their delays."""

import struct


def _lzw_decode(data: bytes, min_size: int) -> list[int]:
    clear, end = 1 << min_size, (1 << min_size) + 1
    size, table, out, prev = min_size + 1, None, [], None
    bits = bitlen = pos = 0

    def reset():
        return [[i] for i in range(clear)] + [[], []]

    table = reset()
    while True:
        while bitlen < size:
            if pos >= len(data):
                return out
            bits |= data[pos] << bitlen
            bitlen += 8
            pos += 1
        code = bits & ((1 << size) - 1)
        bits >>= size
        bitlen -= size
        if code == clear:
            table, size, prev = reset(), min_size + 1, None
            continue
        if code == end:
            return out
        if code < len(table):
            entry = table[code]
            if prev is not None:
                table.append(prev + entry[:1])
        else:
            entry = prev + prev[:1]
            table.append(entry)
        out.extend(entry)
        prev = entry
        if len(table) == (1 << size) and size < 12:
            size += 1


def decode(gif: bytes):
    assert gif[:6] == b"GIF89a"
    width, height, flags = struct.unpack("<HHB", gif[6:11])
    pos = 13
    palette = []
    if flags & 0x80:
        count = 2 << (flags & 7)
        palette = [tuple(gif[pos + i * 3:pos + i * 3 + 3]) for i in range(count)]
        pos += count * 3
    canvas = [0] * (width * height)
    frames, delay, transparent, loops = [], 0, None, None
    while True:
        tag = gif[pos]
        pos += 1
        if tag == 0x3B:
            return {"width": width, "height": height, "palette": palette, "frames": frames, "loop": loops}
        if tag == 0x21:
            label = gif[pos]
            pos += 1
            blocks = b""
            while gif[pos]:
                blocks += gif[pos + 1:pos + 1 + gif[pos]]
                pos += 1 + gif[pos]
            pos += 1
            if label == 0xF9:
                packed, delay, tindex = struct.unpack("<BHB", blocks[:4])
                transparent = tindex if packed & 1 else None
            elif label == 0xFF and blocks.startswith(b"NETSCAPE2.0"):
                loops = struct.unpack("<H", blocks[12:14])[0]
            continue
        assert tag == 0x2C
        x, y, w, h, lflags = struct.unpack("<HHHHB", gif[pos:pos + 9])
        pos += 9
        assert not lflags & 0x80
        min_size = gif[pos]
        pos += 1
        data = b""
        while gif[pos]:
            data += gif[pos + 1:pos + 1 + gif[pos]]
            pos += 1 + gif[pos]
        pos += 1
        pixels = _lzw_decode(data, min_size)[:w * h]
        for row in range(h):
            for col in range(w):
                value = pixels[row * w + col]
                if value != transparent:
                    canvas[(y + row) * width + x + col] = value
        frames.append((bytes(canvas), delay))
        transparent = None
