"""Shared access to the single global /proc/acpi/call kernel node.

The TDP ALIB backend and the Legion fan backend both write this one node, and a
write-then-read is how acpi_call returns a method's result, so a module-level lock
serializes each pair to stop the two backends tearing each other's response.
"""

import os
import subprocess
import threading

from sysfs import read_str, write_str

CALL_REL = "proc/acpi/call"
_LOCK = threading.Lock()


def serialized_call(path: str, command: str):
    """Write *command* and return its echoed result, holding the lock across the
    write+read. None if the write fails."""
    with _LOCK:
        if not write_str(path, command):
            return None
        return read_str(path)


def node_writable(root: str = "/") -> bool:
    p = os.path.join(root, CALL_REL)
    return os.path.exists(p) and os.access(p, os.W_OK)


def module_loadable(root: str = "/") -> bool:
    """True if acpi_call is in the running kernel's module index (a deferred modprobe
    can then succeed). Line-by-line with an early break, never slurps modules.dep."""
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
    """Decided without shelling out (safe on the asyncio loop): node already writable
    or acpi_call loadable. The modprobe itself is deferred off-loop to the first write."""
    return node_writable(root) or module_loadable(root)


def default_modprobe(module: str = "acpi_call") -> None:
    # Decky's PyInstaller-frozen loader hands children an empty PATH + a poisoned
    # LD_LIBRARY_PATH, so a bare "modprobe" silently no-ops. Resolve the absolute
    # binary and restore a sane env, as the other module loaders do.
    from controllers.detect import clean_env, resolve_bin
    subprocess.run([resolve_bin("modprobe"), module],
                   capture_output=True, timeout=5, env=clean_env())
