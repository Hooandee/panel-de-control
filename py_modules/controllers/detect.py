"""Detect which controller manager owns the gamepad on this handheld.

On every target device the raw controller is exclusively grabbed by a resident
daemon — Handheld Daemon (HHD) on Bazzite, InputPlumber on SteamOS — which also
owns button/paddle remapping. Panel de Control NEVER grabs evdev itself (that
would fight the daemon and break input, the same lesson as the display color
work); instead it cooperates with whichever manager is present. This module
identifies it so the Mandos UI can drive the right backend.
"""
import os
import subprocess

HHD = "hhd"
INPUTPLUMBER = "inputplumber"
NONE = "none"

# Common absolute locations for system binaries. The Decky plugin backend can run
# with a MINIMAL PATH (observed on SteamOS: systemctl/busctl not found by name →
# detection wrongly reported "none"), so we resolve to an absolute path and only
# fall back to the bare name (PATH) as a last resort.
_BIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def resolve_bin(name: str) -> str:
    for d in _BIN_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return name


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


def resolve(facts: dict) -> dict:
    """Pure: decide the active controller manager from probed facts.

    HHD takes precedence over InputPlumber — they don't run together in
    practice (HHD is the Bazzite grabber, IP the SteamOS one), but if both were
    reported active HHD is the one that grabbed the controller first.
    """
    if facts.get("hhd_active"):
        return {"manager": HHD, "version": facts.get("hhd_version"), "api": "rest"}
    if facts.get("ip_active"):
        return {"manager": INPUTPLUMBER, "version": facts.get("ip_version"), "api": "dbus"}
    return {"manager": NONE, "version": None, "api": None}


def _run(cmd, timeout=3) -> str:
    """Run a command and return trimmed stdout; "" on any failure (never raises).
    Resolves the binary to an absolute path (plugin env may lack a full PATH)."""
    try:
        cmd = [resolve_bin(cmd[0]), *cmd[1:]]
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=clean_env()
        ).stdout.strip()
    except Exception:
        return ""


def _version_tail(text: str):
    """Last whitespace token of a `<tool> x.y.z` line, or None if empty."""
    return text.split()[-1] if text else None


def probe(run=_run) -> dict:
    """Impure: gather manager facts from the system. Never raises."""
    hhd = run(["systemctl", "is-active", "hhd.service"]) == "active"
    ip = run(["systemctl", "is-active", "inputplumber.service"]) == "active"
    return {
        "hhd_active": hhd,
        "hhd_version": _version_tail(run(["hhd", "--version"])) if hhd else None,
        "ip_active": ip,
        "ip_version": _version_tail(run(["inputplumber", "--version"])) if ip else None,
    }


def detect(run=_run) -> dict:
    """Top-level: resolve the active manager (probe + resolve)."""
    return resolve(probe(run))
