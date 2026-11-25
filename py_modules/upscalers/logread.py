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
    # XeSS D3D11 also calls NGX internally: this names the backend, not the game's input.
    ("d3d11_upscaler", re.compile(r"NVSDK_NGX_D3D11_CreateFeature Creating new (.+?)(?: w/Dx1[12])? feature")),
    # CreateDLSSContext is also an internal helper for XeSS and FSR, so only identify their API entry points.
    ("xess_input", re.compile(r"(?:^|\]\s+)hk_xess(?:D3D11|D3D12|VK)Execute\s*$")),
    ("fsr_input", re.compile(r"\bffxFsr([23])ContextCreate_(?:Dx11|Dx12|Vk) context created:")),
    ("ffx_input", re.compile(r"(ffxCreateContext_Dx12) context created")),
    ("fg_state", re.compile(r"D3D12_Configure Enabled: (true|false), result|SetEnabled: (true|false), result")),
    ("fg_input", re.compile(r"FrameGen\.FGInput: (\w+)")),
    # The game's XeFG stays its own when OptiScaler cannot take over its library: no log line, no End key.
    ("fg_blind", re.compile(r"XeFG passthrough: (false)\s*$")),
    ("fg_context", re.compile(r"(FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0|XeFG context created)")),
    ("upscaler", re.compile(r"init successful for (.+?), upscaler changed")),
    ("fg", re.compile(r"(D3D12_Configure Enabled: true, result: (?:0\b|FFX_API_RETURN_OK)|SetEnabled: true, result: \w*SUCCESS|Nukem.{0,40}(?:initialized|loaded))", re.I)),
    # Queried while loading, whether or not FSR runs later: only names what an FSR feature runs.
    ("fsr4_model", re.compile(r"Upscaler support - fsr4: ([a-z0-9 ]+?)(?: \(forced\))?,")),
    ("fsr4_provider", re.compile(r"QueryProvider \S+ provider for 10000: (4\.\d+\.\d+) \*")),
    ("initial_resolution", re.compile(r"Render Resolution:\s*(\d{2,5})x(\d{2,5}),\s*Display Resolution\s*(\d{2,5})x(\d{2,5})")),
)
# OptiScaler cannot hand a Vulkan game's textures to FSR 4 (D3D12 only) and drops to an older FSR.
_TEXTURE_FAILURE = re.compile(r"CreateSharedTexture Failed to get memory Win32 handle|Can't process Vulkan textures")
_CLOCK = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\.\d+\]")
_FSR4_MODELS = {"int8 lite": "Lite", "int8": "INT8", "fp8": "FP8"}
# An error line and, when it names one, the function that logged it (without OptiScaler's anonymous-namespace prefix).
_ERROR = re.compile(r"\[(?:E|C)\]\s\s*(?:(?:`anonymous-namespace'::)?([A-Za-z_][\w:]{0,60}))?")
ERROR_SOURCES = 6


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
    sources: dict[str, int] = {}
    for line in text.splitlines():
        for key, pattern in _FACTS:
            match = pattern.search(line)
            if not match:
                continue
            if key == "ffx_input":
                facts["input"] = "FSR3"
            elif key == "xess_input":
                facts["input"] = "XeSS"
            elif key == "fsr_input":
                facts["input"] = "FSR" + match.group(1)
            elif key == "d3d11_upscaler":
                facts["upscaler"] = match.group(1).strip()[:120]
            elif key == "initial_resolution":
                facts[key] = {
                    "render": [int(match.group(1)), int(match.group(2))],
                    "output": [int(match.group(3)), int(match.group(4))],
                }
            else:
                facts[key] = next(g for g in match.groups() if g is not None).strip()[:120]
        if error := _ERROR.search(line):
            errors += 1
            if error[1]:
                sources[error[1]] = sources.get(error[1], 0) + 1
        if _TEXTURE_FAILURE.search(line):
            facts["texture_failure"] = True
    # OptiFG starts generating as soon as its context exists and logs no activation until toggled;
    # inputs from the game's own generator wait for the game to switch it on.
    context = facts.pop("fg_context", None)
    if context and facts.pop("fg_input", "").lower() == "upscaler":
        facts.setdefault("fg", context)
    facts.pop("fg_input", None)
    facts["resolution_source"] = "initialization_only" if "initial_resolution" in facts else "unavailable"
    facts["errors"] = errors
    if sources:
        facts["error_sources"] = dict(sorted(sources.items(), key=lambda item: -item[1])[:ERROR_SOURCES])
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
    # OptiScaler's FSR entry points (`fsr31`, `FSR 3.X`, `FSR 3.X/4`) run the FSR 4 provider it selected.
    older = bool(_OLD_FSR.fullmatch(str(facts.get("upscaler") or "").strip()))
    version = facts.get("fsr4_provider") if family == "fsr" and not older and not facts.get("texture_failure") else None
    model = _FSR4_MODELS.get(str(facts.get("fsr4_model") or "")) if version else None
    return {"provider_family": family,
            "provider_name": {"fsr": "FSR", "dlss": "DLSS", "xess": "XeSS"}.get(family),
            "provider_version": version,
            "provider_model": model,
            "provider_source": "optiscaler_log" if available else "unavailable",
            "provider_confidence": "log_provider" if version else "family_only" if family else "unknown"}


_OLD_FSR = re.compile(r"FSR (?:(2)\.(\d+)|(3)\.(\d+))(?:\.\d+)?")


def fallback(install: dict, facts: dict) -> dict | None:
    """FSR 4 was installed but the log shows OptiScaler running an older FSR (or failing to feed it textures).

    `fsr31` and `FSR 3.X/4` are not an older FSR: with FSR 4 they are the entry point it runs through.
    """
    if install.get("engine", "optiscaler") != "optiscaler" or not str(install.get("build", "")).startswith("fsr-4"):
        return None
    if not facts.get("present") or facts.get("stale"):
        return None
    token = str(facts.get("upscaler") or "").strip()
    if token.startswith("FSR 4"):
        return None
    old = _OLD_FSR.fullmatch(token)
    texture = bool(facts.get("texture_failure"))
    if not old and not texture:
        return None
    observed = f"FSR {old[1] or old[3]}.{old[2] or old[4]}" if old else None
    return {"requested": "FSR 4", "observed": observed, "reason": "vulkan_textures" if texture else "backend_changed"}


# ANR FG logs a pacing summary every 10 s while it evaluates; End stops the evaluations and the summaries.
_ANR_PACING = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.\d+\] \[info\] pacing: \d+ real frames .*?evaluates ours (\d+)", re.M)
_ANR_LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.\d+\]", re.M)
ANR_FRESH_S = 25


def _clock_s(hours: str, minutes: str, seconds: str) -> int:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


def anr_generating(folder: Path, now: float) -> bool | None:
    """Whether ANR FG generated in the last summaries of its newest log; None before it wrote one."""
    try:
        newest = max(folder.glob("nr_fg-*.log"), key=lambda path: path.stat().st_mtime)
        modified = newest.stat().st_mtime
        with open(newest, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 64 * 1024))
            tail = handle.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    summaries = _ANR_PACING.findall(tail)
    if not summaries:
        return None
    *clock, ours = summaries[-1]
    # Other lines may keep the file fresh after End: the summary itself must be among the newest.
    since_summary = (_clock_s(*_ANR_LINE.findall(tail)[-1]) - _clock_s(*clock)) % 86400
    return int(ours) > 0 and now - modified <= ANR_FRESH_S and since_summary <= ANR_FRESH_S
