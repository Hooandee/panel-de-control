"""Detect launch-option capabilities from an installed Proton build. Never raises."""

import os
import re

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


def _steam_roots(home: str) -> list:
    return [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam")]


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
    for root in _steam_roots(home):
        # Custom tools (GE-Proton, Proton-CachyOS, …) keep their exact folder name.
        p = os.path.join(root, "compatibilitytools.d", compat_name, "proton")
        if os.path.isfile(p):
            return p
    folder = _builtin_folder(compat_name)
    if folder:
        for root in _steam_roots(home):
            p = os.path.join(root, "steamapps", "common", folder, "proton")
            if os.path.isfile(p):
                return p
    return None


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
            with open(path, errors="ignore") as f:
                detected = set(_CORE) | set(_ENV_RE.findall(f.read()))
            if os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(path)), _OFFICIAL_FSR4_DLL)):
                detected.add("FSR4_UPGRADE")
            envs = sorted(detected)
            found = True
    except Exception:  # noqa: BLE001
        pass
    return {"envs": envs, "found": found}
