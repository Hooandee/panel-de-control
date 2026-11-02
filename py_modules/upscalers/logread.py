"""What OptiScaler actually did, read from the log it writes beside the game.

OptiScaler has no IPC; its log is the only evidence Panel accepts before calling
an install active.
"""

import re
from pathlib import Path

LOG_NAME = "OptiScaler.log"
MAX_BYTES = 4 * 1024 * 1024

_FACTS = (
    ("version", re.compile(r"OptiScaler\s+v?(\d+\.\d+[\w.\-]*)")),
    ("proxy", re.compile(r"OptiScaler working as ([A-Za-z0-9_]+\.(?:dll|asi))", re.I)),
    ("gpu", re.compile(r"Adapter Desc:\s*(.+)")),
    ("upscaler", re.compile(r"Creating new (.+?) upscaler")),
    ("upscaler", re.compile(r"init successful for (.+?), upscaler changed")),
    ("fsr4", re.compile(r"(FSR\s*4[\w.\s]*?(?:INT8|FP8|model\s*\d)[^\n]*)", re.I)),
    ("resolution", re.compile(r"Render\w*\s*[:=]?\s*(\d{3,5})\s*x\s*(\d{3,5}).{0,40}?(?:Display|Output|Target)\w*\s*[:=]?\s*(\d{3,5})\s*x\s*(\d{3,5})", re.I)),
)
_ERROR = re.compile(r"\[(?:E|C)\]\s")


def read(target: Path, since: float | None = None) -> dict:
    """Facts from the newest log; `stale` when it predates `since` (the install)."""
    path = target / LOG_NAME
    try:
        stat = path.stat()
        with open(path, "rb") as handle:
            if stat.st_size > MAX_BYTES:
                handle.seek(stat.st_size - MAX_BYTES)
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return {"present": False}

    facts: dict = {"present": True, "modified": stat.st_mtime}
    if since is not None and stat.st_mtime < since:
        facts["stale"] = True
        return facts
    errors = 0
    for line in text.splitlines():
        for key, pattern in _FACTS:
            match = pattern.search(line)
            if not match:
                continue
            if key == "resolution":
                facts[key] = {
                    "render": [int(match.group(1)), int(match.group(2))],
                    "output": [int(match.group(3)), int(match.group(4))],
                }
            else:
                facts[key] = match.group(1).strip()[:120]
        if _ERROR.search(line):
            errors += 1
    facts["errors"] = errors
    return facts


def verdict(facts: dict) -> str:
    if not facts.get("present"):
        return "not_run"
    if facts.get("stale"):
        return "not_run"
    if facts.get("upscaler"):
        return "active"
    return "loaded"
