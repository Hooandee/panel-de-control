"""User-defined launch variables — durable store shape coercion.

A custom var is a small dict the user defines once and reuses across games. The
frontend validates on entry; this coerces the persisted list before use so a
corrupt or old store can never break the panel. Mirrors validateCustomVar. Never
raises. Unknown fields and unsafe or duplicate tokens are dropped.
"""

import re

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSAFE_RE = re.compile(r"""[\s"'\\`$;&|<>()]""")
_RESERVED_TOKENS = frozenset(
    {
        "LANG",
        "PROTON_FORCE_LARGE_ADDRESS_AWARE",
        "PROTON_NO_FSYNC",
        "PROTON_NO_NTSYNC",
        "PROTON_USE_WINED3D",
        "PROTON_LOG",
        "PROTON_HEAP_DELAY_FREE",
        "PROTON_FSR4_UPGRADE",
        "PROTON_FSR4_RDNA3_UPGRADE",
        "PROTON_USE_OPTISCALER",
        "PROTON_ENABLE_HDR",
        "PROTON_ENABLE_WAYLAND",
        "VKD3D_CONFIG",
        "PROTON_DXVK_D3D8",
        "WINEDLLOVERRIDES",
        "PROTON_PREFER_SDL",
        "-novid",
        "-vulkan",
        "-dx11",
        "-dx12",
        "-windowed",
        "-fullscreen",
        "-nojoy",
        "-high",
    }
)


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
    retired = entry.get("retired") is True
    if kind == "env":
        env_name = entry.get("envName")
        if not isinstance(env_name, str) or not _ENV_NAME_RE.match(env_name):
            return None
        env_value = entry.get("envValue")
        if not isinstance(env_value, str):
            env_value = ""
        if _UNSAFE_RE.search(env_value):
            return None
        clean = {"id": id_, "name": name, "kind": "env", "envName": env_name, "envValue": env_value}
    if kind == "arg":
        arg = entry.get("arg")
        if not isinstance(arg, str) or not arg.strip() or _UNSAFE_RE.search(arg):
            return None
        clean = {"id": id_, "name": name, "kind": "arg", "arg": arg}
    if kind not in ("env", "arg"):
        return None
    if retired:
        clean["retired"] = True
    return clean


def coerce_custom_vars(raw):
    """Return a clean list of valid custom-var dicts, dropping anything malformed."""
    if not isinstance(raw, list):
        return []
    out = []
    seen_ids = set()
    seen_tokens = set(_RESERVED_TOKENS)
    for entry in raw:
        clean = _coerce_one(entry)
        if clean is None:
            continue
        token = clean.get("arg") if clean["kind"] == "arg" else clean.get("envName")
        if clean["id"] in seen_ids or token in seen_tokens:
            continue
        seen_ids.add(clean["id"])
        seen_tokens.add(token)
        out.append(clean)
    return out
