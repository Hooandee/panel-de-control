"""Settings a recipe sets in the game's own config file inside its Proton prefix, undone on removal.

One XML element's text per entry (`<API>kSettingAPI_Vulkan</API>`): written in place so the rest of the file stays
byte for byte, and only put back while it still holds what Panel wrote.
"""

import os
import re
from pathlib import Path

from . import games, ownership

MAX_BYTES = 512 * 1024
USER = "pfx/drive_c/users/steamuser"


def prefix_user(home: str, installed: games.Installed) -> Path | None:
    """The prefix's user folder Steam uses for this game: beside the game when an old library left another."""
    if installed.shortcut or installed.native or not installed.appid.isdecimal():
        return None
    found = [library / "steamapps/compatdata" / installed.appid for library in games.library_paths(home)]
    found = [compat for compat in found if (compat / "pfx").is_dir() and not (compat / "pfx").is_symlink()]
    beside = [compat for compat in found if Path(installed.root).is_relative_to(compat.parent.parent.parent)]
    chosen = beside if len(beside) == 1 else found
    return chosen[0] / USER if len(chosen) == 1 else None


def _element(tag: str) -> re.Pattern:
    return re.compile(rf"(<{re.escape(tag)}>)([^<]{{0,200}})(</{re.escape(tag)}>)")


def _read(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        # Bytes, not text mode: the game's CRLF line ends stay as they are.
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.pdc")
    temporary.write_bytes(text.encode("utf-8"))
    os.chmod(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)
    ownership.own_like(path.parent, [path])


def apply(user: Path | None, entries) -> list[dict]:
    records = []
    for relative, tag, value in entries:
        record = {"file": relative, "tag": tag, "value": value, "state": "missing"}
        records.append(record)
        path = user / relative if user else None
        text = _read(path) if path else None
        match = _element(tag).search(text) if text is not None else None
        if not match:
            continue
        record.update(before=match[2], path=str(path))
        if match[2] == value:
            record["state"] = "already"
            continue
        try:
            _write(path, text[:match.start(2)] + value + text[match.end(2):])
            record["state"] = "set"
        except OSError:
            record["state"] = "failed"
    return records


def restore(records) -> None:
    for record in records or ():
        if not isinstance(record, dict) or record.get("state") != "set" or not record.get("path"):
            continue
        path = Path(record["path"])
        text = _read(path)
        match = _element(str(record.get("tag"))).search(text) if text is not None else None
        # The user (or the game) changed it since: theirs now.
        if not match or match[2] != record.get("value"):
            continue
        try:
            _write(path, text[:match.start(2)] + str(record.get("before", "")) + text[match.end(2):])
        except OSError:
            pass
