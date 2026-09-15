import os
from pathlib import Path


def process_activity(home, proc_root="/proc", data_roots=()):
    result = {"complete": True, "appids": [], "paths": []}
    appids = set()
    paths = set()
    try:
        uid = os.stat(home).st_uid
        processes = list(Path(proc_root).iterdir())
    except OSError:
        return {**result, "complete": False}
    for process in processes:
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != uid:
                continue
            with open(process / "environ", "rb") as source:
                raw = source.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                result["complete"] = False
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
            if not process_appids and not prefix and command.startswith(("wine", "fossilize", "pressure-vessel")):
                result["complete"] = False
            if data_roots:
                links = [process / "cwd"]
                try:
                    links.extend((process / "fd").iterdir())
                except FileNotFoundError:
                    if process.exists():
                        result["complete"] = False
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
            result["complete"] = False
    result["appids"] = sorted(appids)
    result["paths"] = sorted(paths)
    return result
