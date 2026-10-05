"""Host OS identity. Reads /etc/os-release; never raises."""

import os


# Under x86 emulation (FEX on ARM handhelds) a path that also exists in the
# emulator's rootfs resolves there, so /etc/os-release names the rootfs distro.
# /proc/self/root is never redirected and is "/" on a native host.
_HOST_ROOT = "/proc/self/root"


def _os_release_paths(root: str) -> list[str]:
    paths = [os.path.join(root, "etc/os-release")]
    if root == "/":
        paths.insert(0, os.path.join(_HOST_ROOT, "etc/os-release"))
    return paths


def _parse_os_release(root: str = "/") -> dict:
    """All KEY=value pairs from /etc/os-release (quotes stripped). {} if unreadable."""
    for path in _os_release_paths(root):
        rel: dict = {}
        try:
            with open(path) as f:
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().split("=", 1)
                        rel[k] = v.strip('"')
        except OSError:
            continue
        return rel
    return {}


def read_os_name(root: str = "/") -> str | None:
    """Human-readable OS name (PRETTY_NAME, else NAME) or None if unreadable."""
    rel = _parse_os_release(root)
    return rel.get("PRETTY_NAME") or rel.get("NAME") or None


def read_os_id(root: str = "/") -> str | None:
    """Lowercase distro id (ID field), e.g. "steamos"/"bazzite"/"cachyos", or None."""
    return _parse_os_release(root).get("ID", "").lower() or None
