"""Pure-Python GIF89a encoder sized for the 64x54 panel.

Frames after the first carry only the bounding box of pixels that changed, with unchanged pixels
inside it marked transparent, so a precomputed hour of clock stays small. Consecutive identical
frames are merged into one longer delay.
"""

import struct
from dataclasses import dataclass

from .codec import HEIGHT, WIDTH

_MAX_DELAY_CS = 65535
_MAX_CODES = 4096


@dataclass(frozen=True)
class Frame:
    pixels: bytes
    delay_cs: int


def encode(frames: list[Frame], palette: list[tuple[int, int, int]], loop: bool = True) -> bytes:
    if not frames:
        raise ValueError("a GIF needs at least one frame")
    if len(palette) > 256:
        raise ValueError("a GIF palette holds at most 256 colours")
    for frame in frames:
        if len(frame.pixels) != WIDTH * HEIGHT:
            raise ValueError("frame size does not match the panel")

    transparent = len(palette) if len(palette) < 256 else None
    table_bits = max(1, (max(len(palette) + (transparent is not None), 2) - 1).bit_length())
    table = list(palette) + [(0, 0, 0)] * ((1 << table_bits) - len(palette))

    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", WIDTH, HEIGHT, 0x80 | 0x70 | (table_bits - 1), 0, 0)
    for rgb in table:
        out += bytes(rgb)
    if loop and len(frames) > 1:
        out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"

    previous = None
    for pixels, delay in _merged(frames):
        if previous is None:
            box, data, use_transparency = (0, 0, WIDTH, HEIGHT), pixels, False
        else:
            box = _changed_box(previous, pixels) or (0, 0, 1, 1)
            data = _crop(pixels, previous, box, transparent)
            use_transparency = transparent is not None
        out += _graphic_control(delay, transparent if use_transparency else None)
        x, y, w, h = box
        out += b"\x2c" + struct.pack("<HHHHB", x, y, w, h, 0)
        min_code = max(2, table_bits)
        out.append(min_code)
        out += _sub_blocks(_lzw(data, min_code))
        previous = pixels
    out.append(0x3B)
    return bytes(out)


def _merged(frames: list[Frame]) -> list[tuple[bytes, int]]:
    merged: list[list] = []
    for frame in frames:
        if merged and merged[-1][0] == frame.pixels:
            merged[-1][1] += frame.delay_cs
        else:
            merged.append([frame.pixels, frame.delay_cs])
    split: list[tuple[bytes, int]] = []
    for pixels, delay in merged:
        while delay > _MAX_DELAY_CS:
            split.append((pixels, _MAX_DELAY_CS))
            delay -= _MAX_DELAY_CS
        split.append((pixels, delay))
    return split


def _graphic_control(delay: int, transparent: int | None) -> bytes:
    packed = (1 << 2) | (1 if transparent is not None else 0)
    return b"\x21\xf9\x04" + struct.pack("<BHB", packed, delay, transparent or 0) + b"\x00"


def _changed_box(before: bytes, after: bytes) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = WIDTH, HEIGHT, -1, -1
    for index in range(WIDTH * HEIGHT):
        if before[index] != after[index]:
            y, x = divmod(index, WIDTH)
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
    if right < 0:
        return None
    return left, top, right - left + 1, bottom - top + 1


def _crop(pixels: bytes, previous: bytes, box, transparent: int | None) -> bytes:
    x, y, w, h = box
    out = bytearray()
    for row in range(y, y + h):
        start = row * WIDTH + x
        for index in range(start, start + w):
            same = transparent is not None and pixels[index] == previous[index]
            out.append(transparent if same else pixels[index])
    return bytes(out)


def _lzw(data: bytes, min_code: int) -> bytes:
    clear, end = 1 << min_code, (1 << min_code) + 1
    codes: dict[bytes, int] = {}
    size = min_code + 1
    next_code = end + 1
    bits = bitlen = 0
    out = bytearray()

    def emit(code: int) -> None:
        nonlocal bits, bitlen
        bits |= code << bitlen
        bitlen += size
        while bitlen >= 8:
            out.append(bits & 0xFF)
            bits >>= 8
            bitlen -= 8

    emit(clear)
    current = b""
    for value in data:
        candidate = current + bytes((value,))
        if len(candidate) == 1 or candidate in codes:
            current = candidate
            continue
        emit(codes[current] if len(current) > 1 else current[0])
        if next_code < _MAX_CODES:
            codes[candidate] = next_code
            next_code += 1
            if next_code > (1 << size) and size < 12:
                size += 1
        else:
            emit(clear)
            codes.clear()
            size = min_code + 1
            next_code = end + 1
        current = bytes((value,))
    if current:
        emit(codes[current] if len(current) > 1 else current[0])
    emit(end)
    if bitlen:
        out.append(bits & 0xFF)
    return bytes(out)


def _sub_blocks(data: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(data), 255):
        block = data[start:start + 255]
        out.append(len(block))
        out += block
    out.append(0)
    return bytes(out)
