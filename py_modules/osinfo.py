"""Host OS identity. Reads /etc/os-release; never raises."""

import os


def read_os_name(root: str = "/") -> str | None:
    """Human-readable OS name (PRETTY_NAME, else NAME) or None if unreadable."""
    try:
        rel = {}
        with open(os.path.join(root, "etc/os-release")) as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    rel[k] = v.strip('"')
        return rel.get("PRETTY_NAME") or rel.get("NAME") or None
    except OSError:
        return None
