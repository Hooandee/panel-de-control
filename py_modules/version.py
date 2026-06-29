import json
import pathlib
from functools import lru_cache

# Decky reads the plugin version from package.json (NOT plugin.json).
_PACKAGE_JSON = pathlib.Path(__file__).resolve().parent.parent / "package.json"


@lru_cache(maxsize=1)
def read_version() -> str:
    # Never raise: a missing/malformed package.json must not turn get_version into a 500.
    try:
        return json.loads(_PACKAGE_JSON.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"
