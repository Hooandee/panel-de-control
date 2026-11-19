"""Read-only evidence of the Luma components used by OptiScaler."""

import struct
from pathlib import Path
from typing import NamedTuple

from . import ini, pe, recipe_catalog

_MAX_ADDON = 32 * 1024 * 1024


class _Mod(NamedTuple):
    addon: str
    shader: str
    markers: tuple[bytes, ...]


# Keyed by the catalog dependency that installs each Luma package; a game's recipe says which one it uses.
_MODS = {
    "luma-ff7": _Mod('Luma-Final Fantasy VII Remake.addon',
                     'Luma/Final Fantasy VII Remake/Luma_FF7R_Output_SDR_Tonemap.hlsl',
                     (b'Final Fantasy VII Remake Luma mod', b'Luma for "Final Fantasy VII Remake" is developed by ')),
    "luma-p5r": _Mod('Luma-Persona 5 Royal.addon', 'Luma/Persona 5 Royal/Luma_DecodeMotionVector.hlsl',
                     (b'Persona 5 Royal Luma mod',)),
    "luma-mrf": _Mod('Luma-Metaphor ReFantazio.addon', 'Luma/Metaphor ReFantazio/Luma_PrepareMotionVector.hlsl',
                     (b'Metaphor: ReFantazio Luma mod',)),
    "luma-gbfr": _Mod('Luma-Granblue Fantasy Relink.addon', 'Luma/Granblue Fantasy Relink/Luma_GBFR_Tonemap.hlsl',
                      (b'Luma for "Granblue Fantasy Relink" is developed by ',)),
    "luma-qb": _Mod('Luma-Quantum Break.addon', 'Luma/Quantum Break/Luma_QB_PreSRDecode.hlsl',
                    (b'Luma for "Quantum Break" is developed by ',)),
    "luma-prey": _Mod('Luma-Prey.addon', 'Luma/Prey/ArkPostEffects_ArkFullscreenTex_0x994768B0.ps_5_0.hlsl',
                      (b'Luma for "Prey" is developed by ',)),
    "luma-dh2": _Mod('Luma-Dishonored 2.addon', 'Luma/Dishonored 2/AA_TAA_0x06BBC941_0x9F77B624.cs_5_0.hlsl',
                     (b'Luma for "Dishonored 2" is developed by ',)),
    "luma-wd2": _Mod('Luma-Watch Dogs 2.addon', 'Luma/Watch Dogs 2/AmbientOcclusionVolume_0x570E07E7.ps_5_0.hlsl',
                     (b'Luma for "Watch Dogs 2" is developed by ',)),
    "luma-ue": _Mod('Luma-Unreal Engine.addon', 'Luma/Unreal Engine/Luma_MotionVec_UE4_Decode.hlsl',
                    (b'Luma for "Unreal Engine" is developed by ',)),
}


def _mod(appid: str) -> _Mod | None:
    game = recipe_catalog.bundled().games.get(str(appid))
    return next((_MODS[dep] for dep in game.dependencies if dep in _MODS), None) if game else None


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
    mod = _mod(appid)
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
