import struct

from upscalers import pe_sign


def make_pe(path, signed, pe32=False, dirs=16):
    """Minimal PE: DOS stub, signature, COFF header, optional header with data directories."""
    magic, header_size, dir_offset = (0x10B, 224, 96) if pe32 else (0x20B, 240, 112)
    optional = bytearray(header_size)
    struct.pack_into("<H", optional, 0, magic)
    struct.pack_into("<I", optional, dir_offset - 4, dirs)
    if dirs > 4:
        struct.pack_into("<II", optional, dir_offset + 4 * 8, 0x400 if signed else 0, 0x200 if signed else 0)
    dos = bytearray(0x40)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    coff = struct.pack("<HHIIIHH", 0x8664, 0, 0, 0, 0, header_size, 0x2022)
    path.write_bytes(bytes(dos) + b"PE\0\0" + coff + bytes(optional))
    return path


def test_signed_and_unsigned_pe32_plus(tmp_path):
    assert pe_sign.inspect(make_pe(tmp_path / "a.dll", True)) == (True, True)
    assert pe_sign.inspect(make_pe(tmp_path / "b.dll", False)) == (True, False)


def test_signed_and_unsigned_pe32(tmp_path):
    assert pe_sign.is_signed(make_pe(tmp_path / "a.dll", True, pe32=True))
    assert not pe_sign.is_signed(make_pe(tmp_path / "b.dll", False, pe32=True))


def test_few_data_directories_means_unsigned(tmp_path):
    assert pe_sign.inspect(make_pe(tmp_path / "a.dll", True, dirs=3)) == (True, False)


def test_non_pe_and_corrupt_files_are_unsigned_without_raising(tmp_path):
    (tmp_path / "t.txt").write_text("hello")
    (tmp_path / "e.dll").write_bytes(b"")
    good = make_pe(tmp_path / "g.dll", True).read_bytes()
    (tmp_path / "c.dll").write_bytes(good[:100])
    (tmp_path / "m.dll").write_bytes(b"MZ" + bytes(10))
    for name in ("t.txt", "e.dll", "c.dll", "m.dll", "missing.dll"):
        assert pe_sign.inspect(tmp_path / name) == (False, False)
