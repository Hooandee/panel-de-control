"""Host OS identity. Reads /etc/os-release; never raises."""

import os


def _parse_os_release(root: str = "/") -> dict:
    """All KEY=value pairs from /etc/os-release (quotes stripped). {} if unreadable."""
    rel: dict = {}
    try:
        with open(os.path.join(root, "etc/os-release")) as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    rel[k] = v.strip('"')
    except OSError:
        return {}
    return rel


def read_os_name(root: str = "/") -> str | None:
    """Human-readable OS name (PRETTY_NAME, else NAME) or None if unreadable."""
    rel = _parse_os_release(root)
    return rel.get("PRETTY_NAME") or rel.get("NAME") or None


def read_os_id(root: str = "/") -> str | None:
    """Lowercase distro id (ID field), e.g. "steamos"/"bazzite"/"cachyos", or None."""
    return _parse_os_release(root).get("ID", "").lower() or None
