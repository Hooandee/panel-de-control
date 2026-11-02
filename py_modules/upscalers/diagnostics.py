"""Everything needed to explain a failing upscaler install from the support bundle alone."""

import os
import platform
import re
from pathlib import Path

from steam_cleaner import vdf

from . import games, logread
from .assets import sha256

INI_KEYS = (
    "Upscalers.Dx11Upscaler", "Upscalers.Dx12Upscaler", "Upscalers.VulkanUpscaler",
    "FSR.Fsr4Update", "FSR.Fsr4ForceEnableInt8", "FSR.Fsr4ForceModel", "FSR.UpscalerIndex",
    "FrameGen.Enabled", "FrameGen.FGInput", "FrameGen.FGOutput", "OptiFG.HUDFix",
    "QualityOverrides.QualityRatioOverrideEnabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness",
    "Plugins.LoadAsiPlugins", "Plugins.LoadCustomAmdxc64OnRdna2", "Spoofing.Dxgi", "Log.LogLevel",
)
_NOTEWORTHY = re.compile(r"\[(?:W|E|C)\]|Creating new|FSR4|Fsr4|FrameGen|FG |XeFG|Nukem|OptiFG|working as|Adapter Desc", re.I)
_SKIP = re.compile(r"VulkanSpoofing|freely downloadable|GitHub :|Nexus  :|paid for these|MULTIPLAYER|-{10}")
LOG_LINES = 60
LINE_CHARS = 220


def _ini_values(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"missing": True}
    values, section = {}, ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif "=" in stripped and not stripped.startswith(";"):
            key, value = stripped.split("=", 1)
            dotted = f"{section}.{key.strip()}"
            if dotted in INI_KEYS:
                values[dotted] = value.strip()
    return values


def _manifest_check(target: Path) -> dict:
    try:
        import json
        manifest = json.loads((target / games.MANIFEST_DIR / "manifest.json").read_text())
    except (OSError, ValueError):
        return {"present": False}
    missing, changed = [], []
    for relative, digest in manifest.get("files", {}).items():
        path = target / relative
        if not path.is_file():
            missing.append(relative)
        elif digest and sha256(path) != digest:
            changed.append(relative)
    return {"present": True, "files": len(manifest.get("files", {})), "missing": missing, "changed": changed,
            "backups": manifest.get("backups", [])}


def _log_excerpt(target: Path) -> list[str]:
    try:
        with open(target / logread.LOG_NAME, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - logread.MAX_BYTES))
            lines = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    picked = [line[:LINE_CHARS] for line in lines if _NOTEWORTHY.search(line) and not _SKIP.search(line)]
    return picked[-LOG_LINES:]


def _steam_config(home: str, appid: str) -> dict:
    """The compatibility tool and launch options Steam will actually use for the game."""
    result: dict = {}
    for root in games.steam_roots(home):
        try:
            mapping = (vdf.read_text(root / "config/config.vdf").get("installconfigstore") or {}) \
                .get("software", {}).get("valve", {}).get("steam", {}).get("compattoolmapping", {})
            tool = mapping.get(appid) if isinstance(mapping, dict) else None
            if isinstance(tool, dict) and tool.get("name"):
                result["compat_tool"] = tool.get("name")
        except (OSError, ValueError, AttributeError):
            pass
        try:
            profiles = [p for p in (root / "userdata").iterdir() if p.name.isdecimal()]
        except OSError:
            profiles = []
        for profile in profiles:
            try:
                apps = (vdf.read_text(profile / "config/localconfig.vdf").get("userlocalconfigstore") or {}) \
                    .get("software", {}).get("valve", {}).get("steam", {}).get("apps", {})
                app = apps.get(appid) if isinstance(apps, dict) else None
                if isinstance(app, dict) and "launchoptions" in app:
                    result["launch_options"] = str(app["launchoptions"])[:400]
            except (OSError, ValueError, AttributeError):
                continue
    return result


def environment() -> dict:
    os_release = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            key, _, value = line.partition("=")
            if key in ("NAME", "VERSION_ID", "BUILD_ID"):
                os_release[key.lower()] = value.strip('"')
    except OSError:
        pass
    return {"kernel": platform.release(), **os_release}


def game_report(home: str, appid: str, entry: dict) -> dict:
    install = entry.get("install") if isinstance(entry.get("install"), dict) else None
    installed = games.find_installed(home, appid)
    report: dict = {
        "appid": appid,
        "name": installed.name if installed else None,
        "state_flags": installed.state_flags if installed else None,
        "manual_exe": entry.get("exe"),
        "install": install,
        "history": (entry.get("history") or [])[-8:],
        "steam": _steam_config(home, appid),
    }
    if install:
        target = Path(install.get("target", ""))
        facts = logread.read(target, since=install.get("installed_at"))
        report.update({
            "manifest": _manifest_check(target),
            "ini": _ini_values(target / "OptiScaler.ini"),
            "log_verdict": logread.verdict(facts),
            "log_facts": facts,
            "log_excerpt": _log_excerpt(target),
        })
    return report
