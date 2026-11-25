from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Optional

_HEAD_BYTES = 256 * 1024
# JPEG headers are walked segment by segment, so a large EXIF or ICC block before the frame header
# is skipped by seeking; this only bounds how many segments a corrupt file can make us visit.
_MAX_JPEG_SEGMENTS = 1024
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


@dataclass(frozen=True)
class ImageInfo:
    """Stored size (before EXIF orientation), the EXIF orientation 1-8, and whether it may be transparent."""

    width: int
    height: int
    orientation: int = 1
    alpha: bool = False

    @property
    def long_side(self) -> int:
        return max(self.width, self.height)

    @property
    def pixels(self) -> int:
        return self.width * self.height


def probe(path: str) -> Optional[ImageInfo]:
    """Reads only the header, so an absurd or corrupt picture is judged without decoding it."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(_HEAD_BYTES)
            info = _jpeg(handle) if head.startswith(b"\xff\xd8") else _parse(head)
    except (OSError, struct.error, IndexError, ValueError):
        return None
    return info if info and info.width > 0 and info.height > 0 else None


def _parse(head: bytes) -> Optional[ImageInfo]:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png(head)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack_from("<HH", head, 6)
        return ImageInfo(width, height, alpha=True)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _webp(head)
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis", b"mif1"):
        return _avif(head)
    return None


def _png(head: bytes) -> Optional[ImageInfo]:
    if head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack_from(">II", head, 16)
    color_type = head[25]
    idat = head.find(b"IDAT")
    trns = head.find(b"tRNS", 0, idat if idat >= 0 else len(head))
    return ImageInfo(width, height, alpha=color_type in (4, 6) or trns >= 0)


def _jpeg(handle: BinaryIO) -> Optional[ImageInfo]:
    handle.seek(2)
    orientation = 1
    for _ in range(_MAX_JPEG_SEGMENTS):
        if handle.read(1) != b"\xff":
            return None
        marker = handle.read(1)
        while marker == b"\xff":
            marker = handle.read(1)
        if not marker:
            return None
        code = marker[0]
        if code == 0x01 or 0xD0 <= code <= 0xD7:
            continue
        raw = handle.read(2)
        if len(raw) < 2:
            return None
        (length,) = struct.unpack(">H", raw)
        if length < 2:
            return None
        if code in _JPEG_SOF:
            segment = handle.read(5)
            height, width = struct.unpack_from(">HH", segment, 1)
            return ImageInfo(width, height, orientation)
        if code == 0xDA:
            return None
        if code == 0xE1:
            segment = handle.read(length - 2)
            if segment.startswith(b"Exif\x00\x00"):
                orientation = _exif_orientation(segment[6:]) or orientation
            continue
        handle.seek(length - 2, os.SEEK_CUR)
    return None


def _exif_orientation(tiff: bytes) -> Optional[int]:
    order = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if order is None:
        return None
    (ifd,) = struct.unpack_from(order + "I", tiff, 4)
    (count,) = struct.unpack_from(order + "H", tiff, ifd)
    for index in range(min(count, 512)):
        entry = ifd + 2 + index * 12
        tag, kind = struct.unpack_from(order + "HH", tiff, entry)
        if tag == 0x0112 and kind == 3:
            (value,) = struct.unpack_from(order + "H", tiff, entry + 8)
            return value if 1 <= value <= 8 else None
    return None


def _webp(head: bytes) -> Optional[ImageInfo]:
    chunk = head[12:16]
    if chunk == b"VP8X":
        flags = head[20]
        width = 1 + int.from_bytes(head[24:27], "little")
        height = 1 + int.from_bytes(head[27:30], "little")
        return ImageInfo(width, height, alpha=bool(flags & 0x10))
    if chunk == b"VP8L":
        (bits,) = struct.unpack_from("<I", head, 21)
        return ImageInfo(1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF), alpha=True)
    if chunk == b"VP8 ":
        width, height = struct.unpack_from("<HH", head, 26)
        return ImageInfo(width & 0x3FFF, height & 0x3FFF)
    return None


def _boxes(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """ISO BMFF boxes between `start` and `end`: (type, content start, box end); stops at a truncated box."""
    offset = start
    while offset + 8 <= end:
        size, kind = struct.unpack_from(">I4s", data, offset)
        header = 8
        if size == 1:
            (size,) = struct.unpack_from(">Q", data, offset + 8)
            header = 16
        elif size == 0:
            size = end - offset
        if size < header or offset + size > end:
            return
        yield kind, offset + header, offset + size
        offset += size


def _avif(head: bytes) -> Optional[ImageInfo]:
    """The primary item's size: a grid (tiled) picture lists each tile's smaller size too. Without a readable
    item map, the largest size listed, which for a grid is the whole picture."""
    meta = next(((start, end) for kind, start, end in _boxes(head, 0, len(head)) if kind == b"meta"), None)
    if meta is None:
        return None
    primary = None
    properties: list[tuple[bytes, int, int]] = []
    associations: Optional[tuple[int, int]] = None
    for kind, start, end in _boxes(head, meta[0] + 4, meta[1]):
        if kind == b"pitm":
            (primary,) = struct.unpack_from(">H" if head[start] == 0 else ">I", head, start + 4)
        elif kind == b"iprp":
            for inner, inner_start, inner_end in _boxes(head, start, end):
                if inner == b"ipco":
                    properties = list(_boxes(head, inner_start, inner_end))
                elif inner == b"ipma":
                    associations = (inner_start, inner_end)
    sizes = {index: struct.unpack_from(">II", head, start + 4) for index, (kind, start, _end) in enumerate(properties, 1) if kind == b"ispe"}
    if not sizes:
        return None
    chosen = _primary_size(head, associations, primary, sizes) if associations and primary is not None else None
    width, height = chosen or max(sizes.values(), key=lambda size: size[0] * size[1])
    return ImageInfo(width, height, alpha=True)


def _primary_size(head: bytes, associations: tuple[int, int], primary: int, sizes: dict[int, tuple[int, int]]) -> Optional[tuple[int, int]]:
    start, end = associations
    version = head[start]
    wide = bool(head[start + 3] & 1)
    (count,) = struct.unpack_from(">I", head, start + 4)
    offset = start + 8
    for _ in range(count):
        if offset >= end:
            return None
        if version < 1:
            (item,) = struct.unpack_from(">H", head, offset)
            offset += 2
        else:
            (item,) = struct.unpack_from(">I", head, offset)
            offset += 4
        links = head[offset]
        offset += 1
        indices = []
        for _ in range(links):
            if wide:
                (raw,) = struct.unpack_from(">H", head, offset)
                indices.append(raw & 0x7FFF)
                offset += 2
            else:
                indices.append(head[offset] & 0x7F)
                offset += 1
        if item == primary:
            return next((sizes[index] for index in indices if index in sizes), None)
    return None
