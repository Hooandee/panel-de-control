"""Detect which PROTON_* env vars a game's Proton build actually supports, by
reading that build's own `proton` script. This is the source of truth (READMEs
lie / lag), and it self-updates for every new Proton version — a launch-option
pill only shows if the game's Proton really honors its variable. Never raises.
"""

import os
import re

_ENV_RE = re.compile(r"""check_environment\(\s*["'](PROTON_[A-Z0-9_]+)["']""")

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


_cache: dict = {}


def detect_capabilities(compat_name: str, home: str | None = None) -> dict:
    """Return {"envs": [PROTON_* vars this build supports], "found": bool}.
    `found` is False when the script couldn't be located → callers stay
    conservative (show only core vars) rather than promise unverified options.
    """
    home = home or os.path.expanduser("~")
    key = (compat_name or "", home)
    if key in _cache:
        return _cache[key]
    envs = set(_CORE)
    found = False
    try:
        path = _find_proton_script(compat_name or "", home)
        if path:
            with open(path, errors="ignore") as f:
                envs |= set(_ENV_RE.findall(f.read()))
            found = True
    except Exception:  # noqa: BLE001
        pass
    result = {"envs": sorted(envs), "found": found}
    _cache[key] = result
    return dict(result)
