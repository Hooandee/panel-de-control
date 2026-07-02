"""Shared sysfs read/write helpers. Never raise — a missing/unreadable attribute
returns None (honest 'unknown'), a failed write returns False.

Consolidation target: fans/hwmon.py, fans/control.py and power/reader.py still
carry their own private copies of these (pre-existing backlog); new code should
import from here, and those can migrate incrementally."""


def read_str(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(path):
    v = read_str(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def write_str(path, value) -> bool:
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True
    except OSError:
        return False
