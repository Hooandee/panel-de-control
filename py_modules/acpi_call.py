"""Shared access to the single global /proc/acpi/call kernel node.

Both the TDP ALIB backend (\\_SB.ALIB) and the Legion fan backend (\\_SB.GZFD)
write this one node. A write immediately followed by a read is how acpi_call
returns a method's result, so two backends interleaving would tear each other's
response. A module-level lock serializes every write-then-read. Both callers are
low frequency (user actions, no re-assert loop) so contention is negligible.

Never raises.
"""

import os
import subprocess
import threading

from sysfs import read_str, write_str

CALL_REL = "proc/acpi/call"
_LOCK = threading.Lock()


def serialized_call(path: str, command: str):
    """Write *command* to the acpi_call node and return its echoed result, holding
    the shared lock across the write+read. Returns None if the write fails."""
    with _LOCK:
        if not write_str(path, command):
            return None
        return read_str(path)


def node_writable(root: str = "/") -> bool:
    p = os.path.join(root, CALL_REL)
    return os.path.exists(p) and os.access(p, os.W_OK)


def module_loadable(root: str = "/") -> bool:
    """True if acpi_call appears in the running kernel's module index (so a deferred
    modprobe can succeed). Line-by-line with an early break, never slurps a large
    modules.dep."""
    try:
        release = os.uname().release
    except OSError:
        return False
    for base in ("usr/lib/modules", "lib/modules"):
        path = os.path.join(root, base, release, "modules.dep")
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "acpi_call" in line:
                        return True
        except OSError:
            continue
    return False


def available(root: str = "/") -> bool:
    """Decided WITHOUT shelling out (safe on the asyncio loop): the node is already
    writable, or acpi_call is loadable. The actual modprobe is deferred to the first
    write (off-loop) via a backend's own ensure-loaded step."""
    return node_writable(root) or module_loadable(root)


def default_modprobe(module: str = "acpi_call") -> None:
    # Decky's PyInstaller-frozen loader hands children an empty PATH + a poisoned
    # LD_LIBRARY_PATH, so a bare "modprobe" silently no-ops. Resolve the absolute
    # binary and restore a sane env, as the other module loaders do.
    from controllers.detect import clean_env, resolve_bin
    subprocess.run([resolve_bin("modprobe"), module],
                   capture_output=True, timeout=5, env=clean_env())
