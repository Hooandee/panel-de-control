"""Assemble a diagnostic bug-report bundle and scrub PII from it.

Split so the tricky parts are pure and unit-testable:
  - redact_text / redact_obj  - strip home paths, hostname, serial-like values
  - tail_logs                 - newest log files, size-capped, redacted
  - build_bundle              - assemble the final dict from already-fetched parts

main.py does the I/O (calls the get_*_state RPCs, reads the stores + log dir) and
hands the pieces here. The bundle is designed to be *diagnosable*: identity +
detected capabilities (many "X doesn't work" reports are "X has no write path on
your device") + a live state snapshot + the persisted stores + the tail of the
plugin logs where tracebacks land. Never raises: a report must go out even if a
piece is missing.
"""
from __future__ import annotations

import glob
import os
import re

# Bump when the bundle shape changes so consumers can adapt.
SCHEMA = 1

_MAX_TEXT = 4000  # user free-text cap (defensive; the UI also limits it)

# Scrub the VALUE of any dict key that looks like a hardware identifier.
_SCRUB_KEY = re.compile(r"serial|uuid|\bmac\b|mac_?addr|hostname|host_name", re.I)
_HOME_PATH = re.compile(r"/home/[^/\s:\"']+")
# Identifiers that can appear inside free text (log lines, dmesg/journal output).
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def redact_text(s, *, home: str | None = None, hostname: str | None = None):
    """Scrub PII from a string: home paths, an explicit hostname, and any MAC/UUID
    that shows up inside log or kernel output. Never touches a bare username token
    (that would nuke 'Steam Deck' when the user is 'deck')."""
    if not isinstance(s, str):
        return s
    s = _HOME_PATH.sub("~", s)
    if home:
        s = s.replace(home.rstrip("/"), "~")
    if hostname and len(hostname) >= 3:
        s = re.sub(rf"\b{re.escape(hostname)}\b", "HOST", s)
    s = _MAC.sub("[mac]", s)
    s = _UUID.sub("[uuid]", s)
    return s


def redact_obj(obj, *, home: str | None = None, hostname: str | None = None):
    """Recursively redact a JSON-ish structure: scrub serial-like key values and
    run redact_text on every string. Idempotent."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SCRUB_KEY.search(k) and isinstance(v, (str, int, float)):
                out[k] = "[redacted]"
            else:
                out[k] = redact_obj(v, home=home, hostname=hostname)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_obj(x, home=home, hostname=hostname) for x in obj]
    return redact_text(obj, home=home, hostname=hostname)


def _tail_file(path: str, n: int) -> str:
    """Last ~n bytes of a file, decoded leniently, with a partial leading line
    dropped so the excerpt starts on a clean line."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - n)
        f.seek(start)
        raw = f.read()
    txt = raw.decode("utf-8", "replace")
    if start > 0:
        nl = txt.find("\n")
        if nl != -1:
            txt = txt[nl + 1:]
    return txt


def tail_logs(
    log_dir: str,
    *,
    max_files: int = 3,
    max_bytes: int = 200_000,
    home: str | None = None,
    hostname: str | None = None,
) -> list[dict]:
    """The tail of the newest *.log files in log_dir (newest first), redacted and
    capped to a shared byte budget. Never raises → returns [] on any problem."""
    try:
        files = sorted(
            glob.glob(os.path.join(log_dir, "*.log")),
            key=os.path.getmtime,
            reverse=True,
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    budget = max_bytes
    for path in files[:max_files]:
        if budget <= 0:
            break
        try:
            data = _tail_file(path, budget)
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "name": os.path.basename(path),
            "text": redact_text(data, home=home, hostname=hostname),
        })
        budget -= len(data)
    return out


# Kernel-side evidence: firmware/hardware write rejections (TDP, fan curves) land
# in dmesg/journal, NOT the plugin's own log. Captured via an injected runner so
# this stays testable without spawning processes.
_KERNEL_CMDS = {
    "dmesg": ["/usr/bin/dmesg", "--ctime", "--level=err,warn"],
    "journal": ["/usr/bin/journalctl", "-b", "-u", "plugin_loader", "-n", "400", "--no-pager"],
}


def kernel_logs(run, *, cap: int = 40_000, home: str | None = None, hostname: str | None = None) -> dict:
    """Tail of dmesg (errors/warnings) + the plugin_loader journal, via run(cmd)->
    str|None. Redacted and size-capped. Never raises."""
    out = {}
    for key, cmd in _KERNEL_CMDS.items():
        try:
            text = run(cmd)
        except Exception:  # noqa: BLE001
            text = None
        out[key] = redact_text(text[-cap:], home=home, hostname=hostname) if text else None
    return out


def capabilities_from(states: dict) -> dict:
    """Distil the per-subsystem detected backends + supported flags from the live
    state dicts. This is the single most useful section for triage: many reports
    are 'X doesn't work' when X simply has no write path on that device."""
    tdp = states.get("tdp") or {}
    fan = states.get("fan_curve") or {}
    batt = (states.get("battery") or {}).get("charge_limit") or {}
    gpu = states.get("gpu") or {}
    color = states.get("color") or {}
    ctl = states.get("controller") or {}
    return {
        "tdp_backend": tdp.get("backend"),
        "tdp_supported": bool(tdp.get("supported")),
        "fan_source": fan.get("source"),
        "fan_supported": bool(fan.get("supported")),
        "fan_mode_based": bool(fan.get("mode_based")),
        "charge_limit_supported": bool(batt.get("supported")),
        "charge_limit_adjustable": bool(batt.get("adjustable")),
        "gpu_clock_supported": bool(gpu.get("supported")),
        "color_supported": bool(color.get("supported")),
        "controller_manager": ctl.get("manager"),
        "controller_kind": ctl.get("kind"),
    }


def build_bundle(
    *,
    app: str,
    categories,
    text,
    environment: dict,
    capabilities: dict,
    state: dict,
    stores: dict,
    logs: list,
    kernel: dict | None = None,
    home: str | None = None,
    hostname: str | None = None,
) -> dict:
    """Assemble the final bundle from already-fetched pieces and redact the whole
    thing again (logs are pre-redacted; this catches the rest)."""
    bundle = {
        "schema": SCHEMA,
        "app": app,
        "categories": list(categories or []),
        "text": (text or "")[:_MAX_TEXT],
        "environment": environment or {},
        "capabilities": capabilities or {},
        "state": state or {},
        "stores": stores or {},
        "logs": logs or [],
        "kernel": kernel or {},
    }
    return redact_obj(bundle, home=home, hostname=hostname)
