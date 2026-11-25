from __future__ import annotations

import os


def clean_env(base=None) -> dict:
    """Env for spawning SYSTEM binaries from Decky's frozen (PyInstaller) backend.

    PyInstaller sets LD_LIBRARY_PATH to its unpacked bundle dir, whose older bundled
    libs (e.g. libcrypto.so.3) POISON child system binaries: systemctl/busctl link
    libsystemd→libcrypto and fail with `OPENSSL_x not found` → detection wrongly
    reported "none". Restore the pre-bundle value PyInstaller saves as
    LD_LIBRARY_PATH_ORIG (or drop it), and ensure a sane PATH.
    """
    env = dict(os.environ if base is None else base)
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    return env


# The Decky backend can run with a minimal PATH (seen on SteamOS: systemctl/busctl not
# found by name), so binaries resolve to an absolute path first and fall back to the name.
_BIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def resolve_bin(name: str) -> str:
    for d in _BIN_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return name
