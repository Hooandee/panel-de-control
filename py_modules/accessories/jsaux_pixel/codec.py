"""Wire format of the JSAUX PIXEL panel firmware.

Frame: b"DY" | version | command | payload length (u16 BE) | payload | CRC16/KERMIT (BE) over
everything before it. The panel echoes a 9-byte frame whose payload byte is 1 on success and 0
on rejection. Content is always a whole 64x54 GIF89a sent in 498-byte chunks; the closing
command only accepts payload 1 (0, 2 and 3 are silently ignored and the GIF is discarded).
"""

import struct
import zlib
from enum import IntEnum

WIDTH = 64
HEIGHT = 54
CHUNK_BYTES = 498
# Provisional until measured on hardware; scenes shrink their segment to stay under it.
MAX_GIF_BYTES = 32768
_MAGIC = b"DY"


class Cmd(IntEnum):
    POWER = 0x01
    BRIGHTNESS = 0x02
    GIF_BEGIN = 0x04
    GIF_END = 0x0B
    ANIMATION = 0x21
    TEST = 0xF0


_CHUNK_VERSION = 2
_CHUNK_COMMAND = 0x02


def kermit(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def frame(version: int, command: int, payload: bytes) -> bytes:
    body = _MAGIC + bytes((version, command)) + struct.pack(">H", len(payload)) + payload
    return body + struct.pack(">H", kermit(body))


def gif_upload(gif: bytes) -> list[bytes]:
    frames = [frame(1, Cmd.GIF_BEGIN, struct.pack(">II", len(gif), zlib.crc32(gif)))]
    for index, start in enumerate(range(0, len(gif), CHUNK_BYTES)):
        chunk = struct.pack(">H", index) + gif[start:start + CHUNK_BYTES]
        frames.append(frame(_CHUNK_VERSION, _CHUNK_COMMAND, chunk))
    frames.append(frame(1, Cmd.GIF_END, b"\x01"))
    return frames


def is_ack(reply: bytes, version: int, command: int) -> bool:
    expected = frame(version, command, b"\x01")
    return reply[:len(expected)] == expected



def is_reply(reply: bytes, version: int, command: int) -> bool:
    return any(reply[:9] == frame(version, command, bytes((status,))) for status in (0, 1))
