"""User-defined launch variables — durable store shape coercion.

A custom var is a small dict the user defines once and reuses across games. The
frontend validates on entry; this coerces the persisted list before use so a
corrupt or old store can never break the panel. Mirrors validateCustomVar. Never
raises. Unknown fields are dropped; duplicate ids keep the first.
"""

import re

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _coerce_one(entry):
    if not isinstance(entry, dict):
        return None
    id_ = entry.get("id")
    name = entry.get("name")
    if not isinstance(id_, str) or not id_:
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    kind = entry.get("kind")
    if kind == "env":
        env_name = entry.get("envName")
        if not isinstance(env_name, str) or not _ENV_NAME_RE.match(env_name):
            return None
        env_value = entry.get("envValue")
        if not isinstance(env_value, str):
            env_value = ""
        return {"id": id_, "name": name, "kind": "env", "envName": env_name, "envValue": env_value}
    if kind == "arg":
        arg = entry.get("arg")
        if not isinstance(arg, str) or not arg.strip():
            return None
        return {"id": id_, "name": name, "kind": "arg", "arg": arg}
    return None


def coerce_custom_vars(raw):
    """Return a clean list of valid custom-var dicts, dropping anything malformed."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for entry in raw:
        clean = _coerce_one(entry)
        if clean is None or clean["id"] in seen:
            continue
        seen.add(clean["id"])
        out.append(clean)
    return out
