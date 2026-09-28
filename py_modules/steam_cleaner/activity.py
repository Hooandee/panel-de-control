import os
import re
from pathlib import Path

SHADER_CACHE = re.compile(r"(/[^\0]*?/steamapps/shadercache/([0-9]{1,10}))(?=/|\0|$)")
PROCESS_NAME = re.compile(r"[a-z0-9._+-]{1,16}")
ACTIVITY_CAUSES = ("proc_unreadable", "environ_too_large", "unidentified", "fd_unreadable", "unreadable")
MAX_CAUSES = 8


def shader_processing(process, environment):
    # Steam starts background shader processing without SteamAppId; its cache
    # directory names the game it works on.
    try:
        with open(process / "cmdline", "rb") as source:
            arguments = source.read(64 * 1024)
    except FileNotFoundError:
        arguments = b""
    sources = (environment.get(b"MESA_GLSL_CACHE_DIR", b""), arguments)
    return {match for source in sources for match in SHADER_CACHE.findall(os.fsdecode(source))}


def process_name(process):
    try:
        name = (process / "comm").read_text(errors="replace").strip().lower()
    except OSError:
        return "unknown"
    return re.sub(r"[^a-z0-9._+-]", "_", name)[:16] or "unknown"


def activity_causes(result):
    causes = result.get("causes") if isinstance(result, dict) else None
    if not isinstance(causes, list):
        return [{"cause": "unreadable", "process": "none"}]
    return [
        {"cause": item["cause"], "process": item["process"]}
        for item in causes[:MAX_CAUSES]
        if isinstance(item, dict) and item.get("cause") in ACTIVITY_CAUSES
        and isinstance(item.get("process"), str) and PROCESS_NAME.fullmatch(item["process"])
    ]


def process_activity(home, proc_root="/proc", data_roots=()):
    result = {"complete": True, "appids": [], "paths": [], "causes": []}
    appids = set()
    paths = set()

    def incomplete(cause, process=None):
        result["complete"] = False
        entry = {"cause": cause, "process": process_name(process) if process else "none"}
        if entry not in result["causes"] and len(result["causes"]) < MAX_CAUSES:
            result["causes"].append(entry)

    try:
        uid = os.stat(home).st_uid
        processes = list(Path(proc_root).iterdir())
    except OSError:
        incomplete("proc_unreadable")
        return result
    for process in processes:
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != uid:
                continue
            with open(process / "environ", "rb") as source:
                raw = source.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                incomplete("environ_too_large", process)
                continue
            environment = dict(part.split(b"=", 1) for part in raw.split(b"\0") if b"=" in part)
            process_appids = set()
            for key in (b"SteamAppId", b"SteamGameId", b"STEAM_COMPAT_APP_ID"):
                value = environment.get(key, b"").decode("ascii", "ignore")
                if value.isdecimal() and int(value) > 0:
                    # SteamGameId encodes shortcut IDs in the upper 32 bits.
                    number = int(value)
                    process_appids.add(str(number >> 32 if number > 0xFFFFFFFF else number))
            appids.update(process_appids)
            prefix = environment.get(b"STEAM_COMPAT_DATA_PATH")
            if prefix:
                paths.add(os.path.realpath(os.fsdecode(prefix)))
            command = (process / "comm").read_text().strip().lower()
            if not process_appids and not prefix and command.startswith("fossilize"):
                caches = shader_processing(process, environment)
                appids.update(appid for _, appid in caches)
                paths.update(os.path.realpath(path) for path, _ in caches)
                if not caches:
                    incomplete("unidentified", process)
            elif not process_appids and not prefix and command.startswith(("wine", "pressure-vessel")):
                incomplete("unidentified", process)
            if data_roots:
                links = [process / "cwd"]
                try:
                    links.extend((process / "fd").iterdir())
                except FileNotFoundError:
                    if process.exists():
                        incomplete("fd_unreadable", process)
                for link in links:
                    try:
                        destination = os.readlink(link)
                        if any(destination == root or destination.startswith(root + os.sep) for root in data_roots):
                            paths.add(destination)
                    except FileNotFoundError:
                        continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, UnicodeError):
            incomplete("unreadable", process)
    result["appids"] = sorted(appids)
    result["paths"] = sorted(paths)
    return result
