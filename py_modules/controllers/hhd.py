"""Minimal client for the Handheld Daemon REST API (localhost, token-auth).

HHD serves its full settings tree + live state at http://127.0.0.1:5335, the
same interface its own frontend uses. Reading it lets us detect the power
conflict (M0) and, cooperatively, drive the controller settings (later
milestones). Token lives at /etc/hhd/.token (world-unreadable → we run as root).
Every call degrades to None on failure — never fake, never raise.
"""
import json
import os
import urllib.request

_TOKEN_REL = "etc/hhd/.token"
_BASE = "http://127.0.0.1:5335/api/v1"


def _token(root: str = "/"):
    try:
        with open(os.path.join(root, _TOKEN_REL)) as f:
            tok = f.read().strip()
        return tok or None
    except Exception:
        return None


def _get(path: str, token: str, timeout: int = 5):
    req = urllib.request.Request(
        _BASE + path, headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _post(path: str, token: str, payload: dict, timeout: int = 5):
    req = urllib.request.Request(
        _BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def read_state(root: str = "/"):
    """Full HHD live-state JSON, or None if HHD isn't reachable."""
    token = _token(root)
    if not token:
        return None
    try:
        return _get("/state", token)
    except Exception:
        return None


def post_state(payload: dict, root: str = "/"):
    """POST a partial state (HHD merges it) and return the full state it echoes
    back — the honest read-back of what actually stuck. None on failure."""
    token = _token(root)
    if not token:
        return None
    try:
        return _post("/state", token, payload)
    except Exception:
        return None
