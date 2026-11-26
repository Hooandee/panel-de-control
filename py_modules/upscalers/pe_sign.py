"""Whether a Windows binary carries an Authenticode signature, read from its PE security directory.

Anti-tamper that closes the game on unsigned code looks at exactly this: a certificate table entry with data.
The signature's validity is not checked; its presence is what distinguishes a vendor build from a CI nightly.
"""

import struct

_SECURITY_DIR = 4
_MAX_DIRS = 16


def _read(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated")
    return data


def inspect(path) -> tuple[bool, bool]:
    """(is_pe, signed). Anything unreadable or malformed is (False, False)."""
    try:
        with open(path, "rb") as handle:
            if _read(handle, 0, 2) != b"MZ":
                return False, False
            pe = struct.unpack("<I", _read(handle, 0x3C, 4))[0]
            if _read(handle, pe, 4) != b"PE\0\0":
                return False, False
            optional = pe + 24
            magic = struct.unpack("<H", _read(handle, optional, 2))[0]
            if magic not in (0x10B, 0x20B):
                return False, False
            directories = optional + (112 if magic == 0x20B else 96)
            count = struct.unpack("<I", _read(handle, directories - 4, 4))[0]
            if count <= _SECURITY_DIR or count > _MAX_DIRS * 2:
                return True, False
            address, size = struct.unpack("<II", _read(handle, directories + _SECURITY_DIR * 8, 8))
            handle.seek(0, 2)
            return True, size > 0 and address >= 0x40 and address + size <= handle.tell()
    except (OSError, ValueError, struct.error):
        return False, False
