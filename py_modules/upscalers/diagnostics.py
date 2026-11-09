"""Everything needed to explain a failing upscaler install from the support bundle alone."""

import math
import os
import platform
import re
import shlex
import time
from pathlib import Path

from steam_cleaner import vdf

from . import games, helixsr, ini, logread, pe
from .assets import sha256

INI_KEYS = (
    "Upscalers.Dx11Upscaler", "Upscalers.Dx12Upscaler", "Upscalers.VulkanUpscaler",
    "FSR.Fsr4GpuSupport", "FSR.Fsr4Model", "FSR.Fsr4Update", "FSR.Fsr4ForceEnableInt8", "FSR.Fsr4ForceModel", "FSR.UpscalerIndex",
    "FrameGen.Enabled", "FrameGen.FGInput", "FrameGen.FGOutput", "OptiFG.HUDFix",
    *(f"QualityOverrides.QualityRatio{mode}" for mode in ("DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance")),
    "QualityOverrides.QualityRatioOverrideEnabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness", "CAS.Enabled", "CAS.MotionSharpnessEnabled", "HelixSR.Int8",
    "Plugins.LoadAsiPlugins", "Plugins.LoadCustomAmdxc64OnRdna2", "Spoofing.Dxgi", "Log.LogLevel",
)
_NOTEWORTHY = re.compile(r"\[(?:W|E|C)\]|Creating new|FSR4|Fsr4|FrameGen|FG |XeFG|Nukem|OptiFG|working as|Adapter Desc", re.I)
_SKIP = re.compile(r"VulkanSpoofing|freely downloadable|GitHub :|Nexus  :|paid for these|MULTIPLAYER|-{10}")
LOG_LINES = 60
LINE_CHARS = 220


REQUEST_KEYS = ("build", "model", "quality", "fg", "fg_route", "proxy", "sharpness", "hud_fix", "confirm_anti_cheat", "key", "value", "key_action", "value_omitted", "multiplier", "flow", "performance", "enabled", "mode", "target_fps", "max_multiplier", "int8", "scaling_enabled", "scaling_factor", "scaling_sharpness")


def fields(value, keys, limit=160):
    if not isinstance(value, dict):
        return {}
    return {key: (item[:limit] if isinstance(item, str) else item)
            for key in keys if isinstance((item := value.get(key)), (str, bool, int, float))}


def with_job_reference(value: dict, key: str) -> dict:
    result = {name: item for name, item in value.items() if name != key}
    identifier = value.get(key)
    if isinstance(identifier, str) and re.fullmatch(r"[0-9a-f]{12}", identifier):
        result[key] = "job-" + "-".join(identifier[index:index + 4] for index in range(0, 12, 4))
    return result


def report_actions(actions) -> list[dict]:
    return [with_job_reference(action, "job_id") for action in (actions or [])[-20:] if isinstance(action, dict)]


def frontend_context(value) -> dict:
    value = value if isinstance(value, dict) else {}
    running = value.get("running")
    result = {key: value[key][:40] for key in ("collected_at", "status") if isinstance(value.get(key), str)}
    result["status"] = result.get("status") if result.get("status") in ("available", "unavailable") else "unavailable"
    result["running"] = None
    if isinstance(running, dict):
        result["running"] = {key: running[key][:256] for key in ("stable_appid", "name") if isinstance(running.get(key), str)}
        live = running.get("live_appid")
        if isinstance(live, (str, int)) and not isinstance(live, bool):
            if re.fullmatch(r"[0-9]{1,20}", str(live)) and int(live) > 0:
                result["running"]["live_appid"] = str(live)
        result["running"]["is_non_steam"] = running.get("is_non_steam") if isinstance(running.get("is_non_steam"), bool) else None
    result["games"] = {}
    games_value = value.get("games")
    if isinstance(games_value, dict):
        for appid, facts in list(games_value.items())[:12]:
            if isinstance(facts, dict) and re.fullmatch(r"[0-9]{1,20}", str(appid)):
                result["games"][str(appid)] = steam_facts(facts)
    return result


# Steam's EAppOwnershipFlags, named so a report reads as a licence, not a number.
_OWNERSHIP = ((1, "subscribed"), (2, "free_license"), (4, "region_restricted"), (32, "shared_license"),
              (64, "free_weekend"), (128, "retail_license"), (256, "license_locked"), (512, "license_pending"),
              (1024, "license_expired"), (2048, "license_permanent"), (4096, "license_recurring"),
              (8192, "license_canceled"), (16384, "auto_grant"), (131072, "rental"), (262144, "site_license"),
              (2097152, "timed_trial"))


def steam_facts(facts: dict) -> dict:
    """What Steam said live about one game; launch options keep only their technical parts."""
    flags = facts.get("ownership_flags")
    result = {
        "ownership": [name for bit, name in _OWNERSHIP if isinstance(flags, int) and not isinstance(flags, bool) and flags & bit],
        "owned_by_user": facts.get("owned_by_user") if isinstance(facts.get("owned_by_user"), bool) else None,
        "free": facts.get("free") if isinstance(facts.get("free"), bool) else None,
        "beta": facts["beta"][:64] if isinstance(facts.get("beta"), str) and re.fullmatch(r"[\w.\- ]{0,64}", facts["beta"]) else None,
        "build_id": facts.get("build_id") if isinstance(facts.get("build_id"), int) and not isinstance(facts.get("build_id"), bool) else None,
        "compat_tool": facts["compat_tool"][:80] if isinstance(facts.get("compat_tool"), str) and re.fullmatch(r"[\w.\- ]{0,80}", facts["compat_tool"]) else None,
    }
    if isinstance(facts.get("launch_options"), str):
        result["launch_live"] = launch_diagnostics(facts["launch_options"][:16384])
    return result


def ini_request(path: Path, key: str, value: str) -> dict:
    requested = {"key": str(key)[:120], "value_omitted": True}
    try:
        sections = ini.schema(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return requested
    matches = [(f"{section['name']}.{item['key']}", item) for section in sections for item in section["keys"]
               if key in (item["key"], f"{section['name']}.{item['key']}")]
    if len(matches) != 1:
        return requested
    dotted, item = matches[0]
    value = str(value).strip()
    scalar = re.fullmatch(r"(?:auto|true|false|[-+]?[0-9]+(?:\.[0-9]+)?)", value, re.I)
    choice = value in (ini._choices(item.get("help", [])) or []) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,39}", value)
    if scalar or choice:
        return {"key": dotted[:120], "value": value[:80]}
    return requested


def components(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:32]:
        if not isinstance(item, dict):
            continue
        identifier, digest = item.get("id"), item.get("sha256")
        if (isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", identifier)
                and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
            result.append({"id": identifier, "sha256": digest})
    return result


def verification_since(install: dict) -> float | None:
    stamps = [value for key in ("installed_at", "verification_since")
              if type(value := install.get(key)) in (int, float) and math.isfinite(value)]
    return max(stamps) if stamps else None


def solution(plan) -> dict | None:
    if not isinstance(plan, dict):
        return None
    def enum(value, allowed):
        return value if isinstance(value, str) and value in allowed else None
    quality = plan.get("quality") if isinstance(plan.get("quality"), dict) else {}
    result = {
        "effective_api": enum(plan.get("effective_api"), {"d3d11", "d3d12", "vulkan"}),
        "api_source": enum(plan.get("api_source"), {"recipe", "detected", "unknown"}),
        "quality": {"owner": enum(quality.get("owner"), {"panel", "game"}),
                    "reason": enum(quality.get("reason"), {"recipe_quality_game"})},
        "blocked_reason": enum(plan.get("blocked_reason"), {"recipe_api_conflict", "recipe_unresolved", "recipe_unsupported", "fg_unsupported"}),
        "recipe_revision": plan.get("recipe_revision") if type(plan.get("recipe_revision")) is int and 0 <= plan["recipe_revision"] <= 1000000 else None,
        "input_reconciled": plan.get("input_reconciled") is True,
        "recommended_input": enum(plan.get("recommended_input"), {"dlss", "fsr", "fsr2", "fsr3", "fsr31", "xess", "DLSS"}),
        "dependencies": [], "fg_plan": None, "offered_fg_plan": None,
        "warning_reason": enum(plan.get("warning_reason"), {"recipe_api_conflict"}),
    }
    dependencies = plan.get("dependencies")
    if isinstance(dependencies, (list, tuple)):
        result["dependencies"] = [value for value in dependencies[:16]
                                  if isinstance(value, str) and re.fullmatch(r"[a-z0-9-]{1,80}", value)]
    def fg_route(value):
        if not isinstance(value, dict):
            return None
        return {"input": enum(value.get("input"), {"upscaler", "dlssg", "nukems", "fsrfg", "xefg"}),
                "output": enum(value.get("output"), {"fsrfg", "xefg", "nukems"}),
                "source": enum(value.get("source"), {"game", "optiscaler"}),
                "follows_game": value.get("follows_game") is True,
                "experimental": value.get("experimental") is True}
    for key in ("fg_plan", "offered_fg_plan"):
        fg = plan.get(key)
        if isinstance(fg, dict):
            routes = fg.get("routes") if isinstance(fg.get("routes"), dict) else {}
            result[key] = {**fg_route(fg), "route": enum(fg.get("route"), {"game", "optiscaler"}),
                           "routes": {name: fg_route(routes[name]) for name in ("game", "optiscaler")
                                      if isinstance(routes.get(name), dict)}}
    return result


def snapshot(install) -> dict:
    try:
        return _snapshot(install)
    except Exception as error:
        return {"at": time.time(), "observed": {"result": "unknown", "error": type(error).__name__}}


def _snapshot(install) -> dict:
    result = {"at": time.time(), "applied": None, "observed": {"result": "not_installed"}}
    if not isinstance(install, dict):
        return result
    applied = fields(install, ("build", "engine", "archive", "proxy", "installed_at", "verification_since", "recipe", "recipe_revision", "game_build"))
    applied["options"] = fields(install.get("options"), REQUEST_KEYS)
    applied["solution"] = solution(install.get("solution"))
    applied["fg_plan"] = solution({"fg_plan": install.get("fg_plan")})["fg_plan"]
    applied["components"] = [{**item, "sha256": "-".join(item["sha256"][index:index + 4] for index in range(0, 64, 4))}
                             for item in components(install.get("components"))]
    if install.get("target") and install.get("engine", "optiscaler") == "optiscaler":
        path = Path(install["target"]) / "OptiScaler.ini"
        applied["ini"] = _ini_values(path)
        applied["advanced"] = [ini_request(path, key, value) for key, value in list(install.get("edited", {}).items())[:40]]
    applied["recipe_dependencies"] = [value for value in install.get("recipe_dependencies", [])[:16]
                                      if isinstance(value, str) and re.fullmatch(r"[a-z0-9-]{1,80}", value)]
    applied["native_dlls"] = [str(value)[:80] for value in install.get("native_dlls", [])[:16]]
    engine = install.get("engine", "optiscaler")
    if engine == "helixsr":
        facts = helixsr.read_install_log(install)
        verdict = helixsr.verdict(facts)
    elif engine in ("dll", "proton"):
        facts, verdict = {"unverifiable": True}, "unverifiable"
    else:
        facts = logread.read(Path(install.get("target", "")), since=verification_since(install))
        verdict = logread.verdict(facts)
    observed = fields(facts, ("present", "stale", "modified", "upscaler", "input", "fg", "errors", "unverifiable"))
    observed.update(result=verdict, source="game_log" if engine not in ("dll", "proton") else "unavailable",
                    injector_version=facts.get("version"),
                    **logread.provider_observation(facts if engine == "optiscaler" else {}))
    observed["resolution_source"] = facts.get("resolution_source", "unavailable")
    for name in ("resolution", "initial_resolution"):
        resolution = facts.get(name)
        if isinstance(resolution, dict):
            observed[name] = {key: value for key, value in resolution.items() if key in ("render", "output")
                              and isinstance(value, list) and len(value) == 2 and all(type(n) is int for n in value)}
    result.update(applied=applied, observed=observed)
    return result


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
                values[dotted] = value.strip()[:160]
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


def _tail(path: Path) -> list[str]:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 64 * 1024))
            lines = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return [line[:LINE_CHARS] for line in lines[-LOG_LINES:]]


_LAUNCH_DLLS = {name.removesuffix('.dll').lower() for name in games.PROXY_NAMES} | {
    'd3d11', 'nvapi', 'nvapi64', 'd3dcompiler_47', 'msvcp140', 'vcruntime140', 'msvcrt40', 'reshade64',
}
_LAUNCH_MODES = {'n', 'b', 'n,b', 'b,n', 'native', 'builtin', 'native,builtin', 'builtin,native', ''}
_LAUNCH_WRAPPERS = {'mako': 'mako', 'mako-run': 'mako', 'mako-launch': 'mako', 'lsfg': 'lsfg', 'lsfg-vk': 'lsfg', 'lsfg-launch': 'lsfg',
                    'mangohud': 'mangohud', 'gamemoderun': 'gamemoderun'}


def launch_diagnostics(value) -> dict:
    result = {'command_placeholder': False, 'render_flags': [], 'wrappers': [],
              'dll_overrides': [], 'omitted_count': 0, 'reshade_redirected': False}
    if not isinstance(value, str):
        return result
    try:
        tokens = shlex.split(value[:16384])
    except ValueError:
        result['omitted_count'] = 1
        return result
    for token in tokens:
        if token == '%command%':
            result['command_placeholder'] = True
        elif token.lower() in ('-dx11', '-d3d11', '-dx12', '-d3d12'):
            flag = 'dx11' if token.lower() in ('-dx11', '-d3d11') else 'dx12'
            if flag not in result['render_flags']:
                result['render_flags'].append(flag)
        elif token.startswith('RESHADE_BASE_PATH_OVERRIDE='):
            result['reshade_redirected'] = bool(token.partition('=')[2])
        elif token.startswith('WINEDLLOVERRIDES='):
            for override in token.partition('=')[2].split(';'):
                names, separator, mode = override.partition('=')
                names = [name.lower().removesuffix('.dll') for name in names.split(',')]
                if separator and all(name in _LAUNCH_DLLS for name in names) and mode.lower() in _LAUNCH_MODES:
                    result['dll_overrides'].extend({'name': name, 'mode': mode.lower()} for name in names)
                else:
                    result['omitted_count'] += 1
        elif '=' not in token and (wrapper := _LAUNCH_WRAPPERS.get(Path(token).name)):
            if wrapper not in result['wrappers']:
                result['wrappers'].append(wrapper)
        else:
            result['omitted_count'] += 1
    if len(value) > 16384:
        result['omitted_count'] += 1
    return result


def provenance(installed) -> dict:
    result = {'store': 'unknown', 'launcher': 'unknown', 'source': 'unknown',
              'license': 'unknown', 'authenticity': 'unknown'}
    if installed is None:
        return result
    if installed.launcher:
        launcher, _, runner = installed.launcher
        result['launcher'] = launcher if launcher in ('heroic', 'lutris') else 'unknown'
        result['source'] = 'launcher_config'
        if launcher == 'heroic':
            result['store'] = {'legendary': 'epic', 'gog': 'gog', 'nile': 'amazon'}.get(runner, 'unknown')
    elif installed.shortcut:
        result['source'] = 'external_shortcut'
    else:
        result.update(store='steam', launcher='steam', source='steam_manifest')
    return result


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
                    result["launch_diagnostics"] = launch_diagnostics(app["launchoptions"])
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


def _report_install(install):
    if not isinstance(install, dict):
        return None
    result = fields(install, ('build', 'engine', 'archive', 'proxy', 'installed_at', 'verification_since',
                             'recipe', 'recipe_revision', 'game_build'))
    result['options'] = fields(install.get('options'), tuple(key for key in REQUEST_KEYS if key not in ('key', 'value')))
    result['components'] = components(install.get('components'))
    result['solution'] = solution(install.get('solution'))
    result['recipe_dependencies'] = [verb for verb in install.get('recipe_dependencies', [])[:16]
                                     if isinstance(verb, str) and re.fullmatch(r'[a-z0-9-]{1,80}', verb)]
    result['native_dlls'] = [name for name in install.get('native_dlls', [])[:16]
                             if isinstance(name, str) and name.lower().removesuffix('.dll') in _LAUNCH_DLLS]
    return result


def _report_history(history):
    if not isinstance(history, list):
        return []
    result = []
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        clean = fields(item, ('build', 'proxy', 'at', 'result', 'recipe', 'recipe_revision', 'game_build'))
        clean['facts'] = fields(item.get('facts'), ('present', 'stale', 'upscaler', 'input', 'fg', 'errors', 'version'))
        result.append(clean)
    return result


def game_report(home: str, appid: str, entry: dict, installed=None) -> dict:
    install = entry.get("install") if isinstance(entry.get("install"), dict) else None
    installed = installed or games.find_installed(home, appid)
    report: dict = {
        "appid": appid,
        "name": installed.name if installed else None,
        "state_flags": installed.state_flags if installed else None,
        "build_id": installed.build_id if installed else None,
        "provenance": provenance(installed),
        "shortcut": installed.shortcut if installed else None,
        "native": installed.native if installed else None,
        "manual_exe_selected": bool(entry.get("exe")),
        "identity": fields(entry.get("identity"), ("steam_appid", "name", "source")),
        "launcher": list(installed.launcher) if installed and installed.launcher else None,
        "actions": report_actions(entry.get("actions")),
        "previous": entry.get("previous"),
        "current": snapshot(install),
        "install": _report_install(install),
        "history": _report_history(entry.get("history")),
        "steam": _steam_config(home, appid),
    }
    if install and install.get("engine") == "helixsr":
        facts = helixsr.read_install_log(install)
        report.update({
            "helixsr_files": Path(install.get("helix_file", "")).is_file(),
            "log_verdict": helixsr.verdict(facts),
            "log_facts": facts,
            "log_excerpt": _tail(Path(facts["path"])) if facts.get("path") else [],
        })
    elif install and install.get("engine") == "dll":
        report.update({"manifest": _manifest_check(Path(install.get("target", ""))),
                       "dll_targets": install.get("dll_targets", []), "log_verdict": "unverifiable"})
    elif install and install.get("engine") == "proton":
        report["log_verdict"] = "unverifiable"
    elif install:
        target = Path(install.get("target", ""))
        facts = logread.read(target, since=verification_since(install))
        report.update({
            "manifest": _manifest_check(target),
            "ini": _ini_values(target / "OptiScaler.ini"),
            "log_verdict": logread.verdict(facts),
            "log_facts": facts,
            "log_excerpt": _log_excerpt(target),
        })
    return report


# Files that load code into a game besides the game itself: whose they are is the first support question.
_LOADER_FILES = ("dxgi.dll", "d3d11.dll", "d3d12.dll", "dinput8.dll", "version.dll", "winmm.dll", "winhttp.dll",
                 "dbghelp.dll", "nvngx.dll", "OptiScaler.dll", "OptiScaler.ini", "ReShade.ini", "ReShade64.dll",
                 "re2_fw_config.txt", "helixsr-install.json", "amd_fidelityfx_dx12.dll")
_LOADER_DIRS = ("reframework", "OptiScaler", "Luma", "D3D12_Optiscaler", "plugins")
# Files that replace Steam's own API layer. Reported as found, never interpreted: support reads them with the
# Steam ownership facts the frontend adds.
_STORE_FILES = ("steam_emu.ini", "steam_settings", "ColdClientLoader.ini", "OnlineFix.ini", "OnlineFix64.dll",
                "cream_api.ini", "SmartSteamEmu.ini", "CODEX.ini", "steam_interfaces.txt")


def game_files(installed, analysis: dict, owned: list[str]) -> dict:
    """What the game folder holds around its executable: the game's own upscalers and anything injected."""
    root = Path(installed.root)
    target = Path(analysis["target"]) if analysis.get("target") else None
    folders = list(dict.fromkeys(f for f in (target, root) if f is not None))
    result: dict = {"exe": analysis.get("exe"), "apis": list(analysis.get("apis") or [])[:6],
                    "anti_cheat": bool(analysis.get("anti_cheat")),
                    "foreign_identity": fields(analysis.get("foreign_identity"), ("engine", "variant", "manifest_error")),
                    "inputs": {}, "loaders": [], "store_files": []}
    mine = {str(name).lower() for name in owned}
    target_prefix = f"{target.relative_to(root).as_posix()}/" if target and target != root and target.is_relative_to(root) else ""

    def owner(relative_to_root: str) -> str:
        path = relative_to_root.lower()
        candidates = {path, path.removeprefix(target_prefix.lower())} if target_prefix else {path}
        if candidates & mine:
            return "panel"
        if any(name.startswith(candidate.rstrip("/") + "/") for candidate in candidates for name in mine):
            return "panel"
        return "other"

    for kind, paths in (analysis.get("inputs") or {}).items():
        found = []
        for relative in list(paths)[:4]:
            item = {"path": str(relative)[:160], "owner": owner(str(relative))}
            if str(relative).lower().endswith(".dll"):
                strings = pe.version_strings(str(root / relative))
                version = strings.get("FileVersion") or strings.get("ProductVersion")
                if version:
                    item["version"] = version[:40]
            found.append(item)
        result["inputs"][str(kind)[:20]] = found
    for folder in folders:
        try:
            names = {entry.name: entry for entry in folder.iterdir()}
        except OSError:
            continue
        for name in _LOADER_FILES + _LOADER_DIRS:
            entry = names.get(name) or next((e for n, e in names.items() if n.lower() == name.lower()), None)
            if entry is None:
                continue
            relative = entry.relative_to(root).as_posix()
            result["loaders"].append({"path": relative[:160], "dir": entry.is_dir(), "owner": owner(relative)})
        for name in _STORE_FILES:
            if any(n.lower() == name.lower() for n in names):
                result["store_files"].append(name)
    # REFramework writes its own folder beside the dinput8.dll Panel placed: it comes with Panel's install.
    if any(item["path"].lower().endswith("dinput8.dll") and item["owner"] == "panel" for item in result["loaders"]):
        for item in result["loaders"]:
            if item["dir"] and item["path"].lower().rsplit("/", 1)[-1] == "reframework":
                item["owner"] = "panel_runtime"
    result["loaders"] = result["loaders"][:24]
    result["store_files"] = sorted(set(result["store_files"]))
    return result


def proton_prefix(home: str, appid: str) -> dict:
    """The Proton that last ran this game's prefix, as the prefix itself records it."""
    for library in games.library_paths(home):
        compat = library / "steamapps/compatdata" / str(appid)
        try:
            version = (compat / "version").read_text(encoding="utf-8", errors="replace").strip().splitlines()[0][:60]
        except (OSError, IndexError):
            continue
        return {"present": (compat / "pfx").is_dir(), "last_proton": version}
    return {"present": False}

