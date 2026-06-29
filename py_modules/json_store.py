import json
import os


def atomic_json_save(path, data):
    """Write JSON atomically: write a .tmp sibling then os.replace into place."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(data, handle)
    os.replace(tmp, path)
