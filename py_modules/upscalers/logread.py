"""What OptiScaler actually did, read from the log it writes beside the game.

OptiScaler has no IPC; its log is the only evidence Panel accepts before calling
an install active.
"""

import re
from datetime import datetime, timedelta
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
    ("ffx_input", re.compile(r"(ffxCreateContext_Dx12) context created")),
    ("fg_state", re.compile(r"D3D12_Configure Enabled: (true|false), result|SetEnabled: (true|false), result")),
    ("fg_input", re.compile(r"FrameGen\.FGInput: (\w+)")),
    # The game's XeFG stays its own when OptiScaler cannot take over its library: no log line, no End key.
    ("fg_blind", re.compile(r"XeFG passthrough: (false)\s*$")),
    ("fg_context", re.compile(r"(FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0|XeFG context created)")),
    ("upscaler", re.compile(r"init successful for (.+?), upscaler changed")),
    ("fg", re.compile(r"(D3D12_Configure Enabled: true, result: (?:0\b|FFX_API_RETURN_OK)|SetEnabled: true, result: \w*SUCCESS|Nukem.{0,40}(?:initialized|loaded))", re.I)),
    ("initial_resolution", re.compile(r"Render Resolution:\s*(\d{2,5})x(\d{2,5}),\s*Display Resolution\s*(\d{2,5})x(\d{2,5})")),
)
_CLOCK = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\.\d+\]")
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
    first = _CLOCK.match(text) if stat.st_size <= MAX_BYTES else None
    if first:
        # OptiScaler starts a fresh log at every launch and stamps lines with the time of day only.
        day = datetime.fromtimestamp(stat.st_mtime)
        started = day.replace(hour=int(first[1]), minute=int(first[2]), second=int(first[3]), microsecond=0)
        if started > day:
            started -= timedelta(days=1)
        facts["started"] = started.timestamp()
    if since is not None and stat.st_mtime < since:
        facts["stale"] = True
        return facts
    errors = 0
    ffx_input = False
    for line in text.splitlines():
        for key, pattern in _FACTS:
            match = pattern.search(line)
            if not match:
                continue
            if key == "ffx_input":
                ffx_input = True
                facts["input"] = "FSR3"
            elif key == "input":
                value = match.group(1)
                # FFX uses the shared CreateDLSSContext path after its own context creation.
                if value == "DLSS" and ffx_input:
                    value = "FSR3"
                else:
                    ffx_input = False
                facts["input"] = value
            elif key == "initial_resolution":
                facts[key] = {
                    "render": [int(match.group(1)), int(match.group(2))],
                    "output": [int(match.group(3)), int(match.group(4))],
                }
            else:
                facts[key] = next(g for g in match.groups() if g is not None).strip()[:120]
        if _ERROR.search(line):
            errors += 1
    # OptiFG starts generating as soon as its context exists and logs no activation until toggled;
    # inputs from the game's own generator wait for the game to switch it on.
    context = facts.pop("fg_context", None)
    if context and facts.pop("fg_input", "").lower() == "upscaler":
        facts.setdefault("fg", context)
    facts.pop("fg_input", None)
    facts["resolution_source"] = "initialization_only" if "initial_resolution" in facts else "unavailable"
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


def provider_observation(facts: dict) -> dict:
    family = None
    available = bool(facts.get("present") and not facts.get("stale"))
    token = facts.get("upscaler") if available else None
    if isinstance(token, str):
        token = token.casefold().strip()
        for candidate in ("fsr", "dlss", "xess"):
            if re.fullmatch(candidate + r"(?:[234]1?| [234](?:\.[0-9x]+)*(?:/4)?(?: lite)?)?", token):
                family = candidate
                break
    return {"provider_family": family,
            "provider_name": {"fsr": "FSR", "dlss": "DLSS", "xess": "XeSS"}.get(family),
            "provider_version": None,
            "provider_source": "optiscaler_log" if available else "unavailable",
            "provider_confidence": "family_only" if family else "unknown"}
