"""Detect launch-option capabilities from an installed Proton build. Never raises."""

import os
import re

from steam_cleaner.vdf import read_text

_ENV_RE = re.compile(r"""check_environment\(\s*["'](PROTON_[A-Z0-9_]+)["']""")
_OFFICIAL_FSR4_DLL = os.path.join("contrib", "amdxcffx64.dll")

# Core Proton vars honored by every build even if not via check_environment
# (PROTON_LOG is handled by the runtime, not the script).
_CORE = (
    "PROTON_LOG",
    "PROTON_USE_WINED3D",
    "PROTON_NO_ESYNC",
    "PROTON_NO_FSYNC",
    "PROTON_FORCE_LARGE_ADDRESS_AWARE",
)


# Distro packages (CachyOS proton-cachyos, Armada's ARM64 builds) register tools system-wide.
SYSTEM_COMPAT_DIRS = (
    "/usr/share/steam/compatibilitytools.d",
    "/usr/local/share/steam/compatibilitytools.d",
)


def _steam_roots(home: str) -> list:
    return [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam")]


def _builtin_folder(compat_name: str) -> str | None:
    """Map a built-in compat-tool id to its steamapps/common folder name."""
    n = (compat_name or "").lower()
    if n.endswith("-arm64"):
        # Valve's ARM64 builds install apart from the x86 ones; never read the x86 folder.
        base = n[: -len("-arm64")]
        if base == "proton-experimental":
            return "Proton Experimental (ARM64)"
        m = re.fullmatch(r"proton_(\d+)", base)
        return f"Proton {m.group(1)}.0 (ARM64)" if m else None
    if "experimental" in n:
        return "Proton - Experimental"
    if n in ("proton_hotfix", "proton_next"):
        return "Proton Hotfix"
    m = re.match(r"proton_(\d+)", n)
    if m:
        return f"Proton {m.group(1)}.0"
    return None


def _custom_proton_script(directory: str, compat_name: str) -> str | None:
    manifest = os.path.join(directory, "compatibilitytool.vdf")
    install_path = "."
    if os.path.lexists(manifest):
        try:
            document = read_text(manifest)
            tool = document["compatibilitytools"]["compat_tools"][compat_name.lower()]
            install_path = tool.get("install_path", ".")
            if not isinstance(install_path, str) or os.path.isabs(install_path):
                return None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
    elif os.path.basename(directory) != compat_name:
        return None
    path = os.path.join(directory, install_path, "proton")
    return path if os.path.isfile(path) else None


def _find_proton_script(compat_name: str, home: str, system_dirs) -> str | None:
    if not compat_name or os.path.basename(compat_name) != compat_name:
        return None
    custom_dirs = [os.path.join(root, "compatibilitytools.d") for root in _steam_roots(home)]
    roots = (*custom_dirs, *system_dirs)
    for directory in roots:
        path = _custom_proton_script(os.path.join(directory, compat_name), compat_name)
        if path:
            return path
    for directory in roots:
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry == compat_name:
                continue
            path = _custom_proton_script(os.path.join(directory, entry), compat_name)
            if path:
                return path
    folder = _builtin_folder(compat_name)
    if folder:
        for root in _steam_roots(home):
            p = os.path.join(root, "steamapps", "common", folder, "proton")
            if os.path.isfile(p):
                return p
    return None


def detect_capabilities(
    compat_name: str, home: str | None = None, system_dirs=SYSTEM_COMPAT_DIRS,
) -> dict:
    """Return {"envs": [launch-option vars this build supports], "found": bool}.
    `found` is False when the build's script couldn't be located (no compat tool, a
    native/non-Steam game, or a missing install). In that case `envs` is empty — we
    never offer Proton options we haven't confirmed against a real build.
    """
    home = home or os.path.expanduser("~")
    envs: list = []
    found = False
    try:
        path = _find_proton_script(compat_name or "", home, system_dirs)
        if path:
            with open(path, errors="ignore") as f:
                detected = set(_CORE) | set(_ENV_RE.findall(f.read()))
            if os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(path)), _OFFICIAL_FSR4_DLL)):
                detected.add("FSR4_UPGRADE")
            envs = sorted(detected)
            found = True
    except Exception:  # noqa: BLE001
        pass
    return {"envs": envs, "found": found}
