"""Detect launch-option capabilities from an installed Proton build. Never raises."""

import os
import re

_ENV_RE = re.compile(r"""check_environment\(\s*["'](PROTON_[A-Z0-9_]+)["']""")
_PROTON_TOKEN_RE = re.compile(r"\bPROTON_[A-Z0-9_]+\b")
# Short upscaler names handled by the CachyOS proton script's compat-config table
# (e.g. "FSR4_UPGRADE" without the PROTON_ prefix).
_SHORT_ENVS = ("FSR4_UPGRADE", "FSR3_UPGRADE", "XESS_UPGRADE", "DLSS_UPGRADE")
_SHORT_RE = re.compile(r"\b(" + "|".join(_SHORT_ENVS) + r")\b")
_OFFICIAL_FSR4_DLL = os.path.join("contrib", "amdxcffx64.dll")

# System-wide compat-tool roots (CachyOS/Arch install Proton-CachyOS here via pacman).
_SYSTEM_COMPAT_ROOTS = (
    "/usr/share/steam/compatibilitytools.d",
    "/usr/local/share/steam/compatibilitytools.d",
)

# Folder-name suffixes that identify the same build as the plain id
# (e.g. "Proton-CachyOS Latest-x86_64_v3" vs "Proton-CachyOS Latest").
_VARIANT_SUFFIXES = (
    "-slr",
    "-native",
    "-x86_64_v2",
    "-x86_64_v3",
    "-x86_64_v4",
    "-ntsync",
    "-bleeding-edge",
)

# Core Proton vars honored by every build even if not via check_environment
# (PROTON_LOG is handled by the runtime, not the script).
_CORE = (
    "PROTON_LOG",
    "PROTON_USE_WINED3D",
    "PROTON_NO_ESYNC",
    "PROTON_NO_FSYNC",
    "PROTON_FORCE_LARGE_ADDRESS_AWARE",
)


def _steam_roots(home: str) -> list:
    return [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam")]


def _compat_roots(home: str) -> list:
    """compatibilitytools.d roots: per-user Steam dirs plus system-wide ones."""
    roots = [os.path.join(root, "compatibilitytools.d") for root in _steam_roots(home)]
    roots.extend(_SYSTEM_COMPAT_ROOTS)
    return roots


def _read_compat_tool_name(folder: str) -> str | None:
    """Read the authoritative compat-tool id from a toolmanifest.vdf, if present."""
    manifest = os.path.join(folder, "toolmanifest.vdf")
    try:
        with open(manifest, errors="ignore") as f:
            m = re.search(r'"compat_tool_name"\s*"([^"]+)"', f.read())
            return m.group(1) if m else None
    except OSError:
        return None


def _compat_id_to_folder(home: str) -> dict:
    """Map compat-tool ids to their folder names across all compat roots.

    The folder name is the display name (e.g. "Proton-CachyOS Latest-x86_64_v3")
    while the id Steam uses is the toolmanifest.vdf "compat_tool_name"
    (e.g. "proton-cachyos-11.0-2026-07-03"). Fall back to the folder name when no
    manifest exists.
    """
    mapping: dict = {}
    for root in _compat_roots(home):
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for name in entries:
            folder = os.path.join(root, name)
            if not os.path.isdir(folder):
                continue
            tool_id = _read_compat_tool_name(folder) or name
            mapping.setdefault(tool_id, folder)
    return mapping


def _builtin_folder(compat_name: str) -> str | None:
    """Map a built-in compat-tool id to its steamapps/common folder name."""
    n = (compat_name or "").lower()
    if "experimental" in n:
        return "Proton - Experimental"
    if n in ("proton_hotfix", "proton_next"):
        return "Proton Hotfix"
    m = re.match(r"proton_(\d+)", n)
    if m:
        return f"Proton {m.group(1)}.0"
    return None


def _find_proton_script(compat_name: str, home: str) -> str | None:
    if not compat_name:
        return None
    # 1) Exact folder-name match (custom tools usually keep their folder name).
    for root in _compat_roots(home):
        p = os.path.join(root, compat_name, "proton")
        if os.path.isfile(p):
            return p
    # 2) Resolve the id through toolmanifest.vdf (folder name may differ, e.g.
    #    "Proton-CachyOS Latest-x86_64_v3" → id "proton-cachyos-11.0-2026-07-03").
    folder = _compat_id_to_folder(home).get(compat_name)
    if folder:
        p = os.path.join(folder, "proton")
        if os.path.isfile(p):
            return p
    # 3) Case-insensitive + known-suffix fallbacks.
    lower = compat_name.lower()
    for root in _compat_roots(home):
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for name in entries:
            if name.lower() == lower or any(
                name.lower() == lower + suffix for suffix in _VARIANT_SUFFIXES
            ):
                p = os.path.join(root, name, "proton")
                if os.path.isfile(p):
                    return p
    # 4) Built-in Proton (steamapps/common).
    folder = _builtin_folder(compat_name)
    if folder:
        for root in _steam_roots(home):
            p = os.path.join(root, "steamapps", "common", folder, "proton")
            if os.path.isfile(p):
                return p
    return None


def _scan_build_envs(build_dir: str) -> set:
    """Collect PROTON_* / short upscaler vars referenced by the build.

    Scans the `proton` script and the `protonfixes/` python package (where modern
    builds moved upscaler handling). Matches check_environment() calls plus any
    PROTON_* token and the short upscaler names.
    """
    detected: set = set()
    targets = [os.path.join(build_dir, "proton")]
    protonfixes = os.path.join(build_dir, "protonfixes")
    if os.path.isdir(protonfixes):
        for dirpath, _dirnames, filenames in os.walk(protonfixes):
            for fn in filenames:
                if fn.endswith(".py"):
                    targets.append(os.path.join(dirpath, fn))
    for path in targets:
        try:
            with open(path, errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        detected.update(_ENV_RE.findall(text))
        detected.update(_PROTON_TOKEN_RE.findall(text))
        detected.update(_SHORT_RE.findall(text))
    return detected


def detect_capabilities(compat_name: str, home: str | None = None) -> dict:
    """Return {"envs": [launch-option vars this build supports], "found": bool}.
    `found` is False when the build's script couldn't be located (no compat tool, a
    native/non-Steam game, or a missing install). In that case `envs` is empty — we
    never offer Proton options we haven't confirmed against a real build.
    """
    home = home or os.path.expanduser("~")
    envs: list = []
    found = False
    try:
        path = _find_proton_script(compat_name or "", home)
        if path:
            build_dir = os.path.dirname(os.path.realpath(path))
            detected = set(_CORE) | _scan_build_envs(build_dir)
            if os.path.isfile(os.path.join(build_dir, _OFFICIAL_FSR4_DLL)):
                detected.add("FSR4_UPGRADE")
            envs = sorted(detected)
            found = True
    except Exception:  # noqa: BLE001
        pass
    return {"envs": envs, "found": found}
