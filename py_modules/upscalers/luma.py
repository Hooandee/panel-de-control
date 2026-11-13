"""Read-only evidence of the Luma components used by OptiScaler."""

import struct
from pathlib import Path
from typing import NamedTuple

from . import ini, pe

_MAX_ADDON = 32 * 1024 * 1024


class _Mod(NamedTuple):
    addon: str
    shader: str
    markers: tuple[bytes, ...]


_MODS = {
    "1462040": _Mod('Luma-Final Fantasy VII Remake.addon',
                    'Luma/Final Fantasy VII Remake/Luma_FF7R_Output_SDR_Tonemap.hlsl',
                    (b'Final Fantasy VII Remake Luma mod', b'Luma for "Final Fantasy VII Remake" is developed by ')),
    "1687950": _Mod('Luma-Persona 5 Royal.addon',
                    'Luma/Persona 5 Royal/Luma_DecodeMotionVector.hlsl',
                    (b'Persona 5 Royal Luma mod',)),
}


def _file(root: Path, target: Path, name: str, limit: int) -> Path | None:
    path = target / name
    if not path.is_relative_to(root):
        return None
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            return None
    try:
        return path if path.is_file() and 0 < path.stat().st_size <= limit else None
    except OSError:
        return None


def _x64_image(data: bytes) -> bool:
    if len(data) < 64 or data[:2] != b'MZ':
        return False
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    return offset <= len(data) - 6 and data[offset:offset + 6] == b'PE\0\0\x64\x86'


def detected(root: Path, target: Path | None, appid: str) -> bool:
    mod = _MODS.get(str(appid))
    if target is None or mod is None:
        return False
    try:
        root = root.resolve(strict=True)
        if target.is_symlink():
            return False
        target = target.resolve(strict=True)
        addon = _file(root, target, mod.addon, _MAX_ADDON)
        loader = _file(root, target, 'ReShade64.dll', _MAX_ADDON)
        settings = _file(root, target, 'OptiScaler.ini', 1024 * 1024)
        shader = _file(root, target, mod.shader, 1024 * 1024)
        compiler = _file(root, target, 'Luma/d3dcompiler_47.dll', _MAX_ADDON)
        if not all((addon, loader, settings, shader, compiler)):
            return False
        if ini.read(settings.read_text(encoding='utf-8', errors='replace'), 'Plugins.LoadReshade').strip().lower() != 'true':
            return False
        identity = pe.version_strings(str(loader))
        if identity.get('ProductName', '').casefold() != 'reshade' or identity.get('OriginalFilename', '').casefold() != 'reshade64.dll':
            return False
        loader_data = loader.read_bytes()
        if not _x64_image(loader_data) or b'ReShadeRegisterAddon' not in loader_data or not _x64_image(compiler.read_bytes()):
            return False
        data = addon.read_bytes()
        return _x64_image(data) and all(marker in data for marker in mod.markers)
    except (OSError, ValueError, AttributeError, struct.error):
        return False
