import json
import os
import tempfile


def atomic_json_save(path, data):
    """Write JSON atomically through a unique sibling before replacing the file."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    target_dir = directory or "."
    basename = os.path.basename(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{basename}.", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
