"""Anatase-owned adapter for cooperative TDP handoff with HHD."""

import json
import os
import urllib.request

from controllers import conflict


_TOKEN_REL = "etc/hhd/.token"
_BASE = "http://127.0.0.1:5335/api/v1"


def _token(root: str = "/"):
    try:
        with open(os.path.join(root, _TOKEN_REL)) as handle:
            token = handle.read().strip()
        return token or None
    except OSError:
        return None


def _get(path: str, token: str, timeout: int = 5):
    request = urllib.request.Request(
        _BASE + path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _post(path: str, token: str, payload: dict, timeout: int = 5):
    request = urllib.request.Request(
        _BASE + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def read_state(root: str = "/"):
    token = _token(root)
    if not token:
        return None
    try:
        return _get("/state", token)
    except Exception:  # noqa: BLE001
        return None


def post_state(payload: dict, root: str = "/"):
    token = _token(root)
    if not token:
        return None
    try:
        return _post("/state", token, payload)
    except Exception:  # noqa: BLE001
        return None


def _tdp_enable(state):
    try:
        value = state["hhd"]["settings"]["tdp_enable"]
    except (KeyError, TypeError):
        return None
    return value if isinstance(value, bool) else None


def current_tdp_enable(root: str = "/"):
    state = read_state(root)
    if _tdp_enable(state) is None:
        return None
    return conflict.hhd_managing_power(state)


def set_tdp_enable(enabled: bool, root: str = "/"):
    post_state(
        {"hhd": {"settings": {"tdp_enable": bool(enabled)}}},
        root,
    )
    return _tdp_enable(read_state(root))
