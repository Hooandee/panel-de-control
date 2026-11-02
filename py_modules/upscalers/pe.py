"""Graphics API of a Windows executable, read from its PE import tables."""

import struct

_GRAPHICS = {
    "d3d12.dll": "d3d12",
    "d3d11.dll": "d3d11",
    "vulkan-1.dll": "vulkan",
    "dxgi.dll": "dxgi",
}
_IMPORT_DIR = 1
_DELAY_IMPORT_DIR = 13
_MAX_DLLS = 512


class _Image:
    def __init__(self, handle):
        self.handle = handle
        self.sections: list[tuple[int, int, int]] = []

    def read(self, offset: int, size: int) -> bytes:
        self.handle.seek(offset)
        data = self.handle.read(size)
        if len(data) != size:
            raise ValueError("truncated")
        return data

    def offset(self, rva: int) -> int | None:
        for virtual, length, raw in self.sections:
            if virtual <= rva < virtual + length:
                return raw + rva - virtual
        return None

    def string(self, rva: int) -> str | None:
        offset = self.offset(rva)
        if offset is None:
            return None
        self.handle.seek(offset)
        raw = self.handle.read(256).split(b"\0", 1)[0]
        return raw.decode("ascii", "replace").lower()


def imported_dlls(path: str) -> set[str]:
    """Lower-case names of every DLL the image imports, delay-loaded included."""
    with open(path, "rb") as handle:
        image = _Image(handle)
        if image.read(0, 2) != b"MZ":
            raise ValueError("not_pe")
        pe = struct.unpack("<I", image.read(0x3C, 4))[0]
        if image.read(pe, 4) != b"PE\0\0":
            raise ValueError("not_pe")
        sections, optional_size = struct.unpack("<H12xH", image.read(pe + 6, 16))
        optional = pe + 24
        magic = struct.unpack("<H", image.read(optional, 2))[0]
        directories = optional + (112 if magic == 0x20B else 96)
        for index in range(sections):
            header = image.read(optional + optional_size + index * 40, 40)
            virtual_size, virtual, raw_size, raw = struct.unpack("<IIII", header[8:24])
            image.sections.append((virtual, max(virtual_size, raw_size), raw))

        names: set[str] = set()
        for directory, entry_size, name_field in ((_IMPORT_DIR, 20, 12), (_DELAY_IMPORT_DIR, 32, 4)):
            rva, size = struct.unpack("<II", image.read(directories + directory * 8, 8))
            start = image.offset(rva) if rva and size else None
            if start is None:
                continue
            for index in range(_MAX_DLLS):
                entry = image.read(start + index * entry_size, entry_size)
                if not any(entry):
                    break
                name = image.string(struct.unpack("<I", entry[name_field:name_field + 4])[0])
                if name:
                    names.add(name)
        return names


def graphics_apis(path: str) -> list[str]:
    try:
        names = imported_dlls(path)
    except (OSError, ValueError, struct.error):
        return []
    return sorted({api for dll, api in _GRAPHICS.items() if dll in names})
