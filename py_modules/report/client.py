"""Send a report bundle to the collector service, with an offline fallback.

The plugin only ever WRITES (POST). There is no read path here - downloading a
report is dev-only and lives in the service, gated by a secret key. Mirrors the
urllib + SSL pattern used by self_updater.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from http_util import ssl_context

_UA = "panel-de-control-reporter"


def parse_response(status: int, body: bytes) -> dict:
    """Shape the service reply into a stable result. Success requires a 2xx AND a
    code (a malformed body is not a success)."""
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        data = {}
    if 200 <= status < 300 and data.get("ok") and data.get("code"):
        return {
            "ok": True,
            "code": str(data["code"]),
            "issue_url": data.get("issueUrl") or data.get("issue_url"),
        }
    err = data.get("error") or f"HTTP {status}"
    return {"ok": False, "error": str(err)}


def submit(service_url: str, payload: dict, *, timeout: int = 20) -> dict:
    """POST the payload as JSON. Returns {ok, code, issue_url} or {ok:false, error}.
    Never raises."""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            service_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": _UA},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:  # noqa: S310
            return parse_response(getattr(resp, "status", 200), resp.read())
    except urllib.error.HTTPError as e:
        try:
            return parse_response(e.code, e.read() or b"")
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def save_local(dir_: str, bundle: dict, *, code: str | None = None) -> str | None:
    """Offline fallback: write the bundle to disk so the user can send it by hand.
    Returns the path, or None if even that failed. Never raises."""
    try:
        os.makedirs(dir_, exist_ok=True)
        name = f"report-{code}.json" if code else "report-offline.json"
        path = os.path.join(dir_, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        return path
    except Exception:  # noqa: BLE001
        return None
