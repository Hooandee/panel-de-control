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
    ("upscaler", re.compile(r"Creating (.+?) upscaler feature")),
    ("input", re.compile(r"Create(DLSS|FSR2|FSR3|XeSS)Context")),
    ("upscaler", re.compile(r"init successful for (.+?), upscaler changed")),
    ("fg", re.compile(r"(D3D12_Configure Enabled: true, result: 0|XeFG context created|Nukem.{0,40}(?:initialized|loaded))", re.I)),
    ("resolution", re.compile(r"Render Resolution:\s*(\d{2,5})x(\d{2,5}),\s*Display Resolution\s*(\d{2,5})x(\d{2,5})")),
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
