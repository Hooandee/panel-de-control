"""Theme health: what CSS Loader will actually load from the themes folder, and a reversible
cleanup that sets aside folders able to restyle Steam without showing up as a normal theme."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

import theme_packages

CLEANUP_DIRECTORY = ".panel-theme-cleanup"
_RECORD = "record.json"
_DAMAGED_RECORD = "record.damaged.json"
_RECORD_SCHEMA = 1
_FOLDER_LIMIT = 200
_MANIFEST_BYTES = 256 * 1024
_NAME_CHARS = 255
# CSS Loader rejects manifests newer than the version it understands (css_theme.CSS_LOADER_VER).
_CSS_LOADER_MANIFEST_VERSION = 9
# Steam Friends Patcher files that CSS Loader injects without a theme.json (css_sfp_compat.py).
_SFP_FILES = (
    "libraryroot.custom.css",
    "bigpicture.custom.css",
    "friends.custom.css",
    "webkit.css",
)
SET_ASIDE_KINDS = frozenset({"legacy", "broken", "leftover", "duplicate"})
_INTERNAL_CONNECTORS = ("eDP", "DSI", "LVDS")


class ThemeHealthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read_manifest(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Returns (manifest, present). A present manifest that CSS Loader cannot use is (None, True)."""
    try:
        if not path.is_file():
            return None, False
        if path.stat().st_size > _MANIFEST_BYTES:
            return None, True
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, True
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not value["name"]:
        return None, True
    try:
        if int(value.get("manifest_version", 1)) > _CSS_LOADER_MANIFEST_VERSION:
            return None, True
    except (TypeError, ValueError):
        return None, True
    return value, True


def _is_active(folder: Path) -> bool:
    try:
        config = json.loads((folder / "config_USER.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and config.get("active") is True


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _has_theme_files(folder: Path) -> bool:
    return _is_file(folder / "theme.css") or any(_is_file(folder / item) for item in _SFP_FILES)


def _classify(folder: Path) -> dict[str, Any] | None:
    manifest, present = _read_manifest(folder / "theme.json")
    if manifest is not None:
        flags = manifest.get("flags")
        preset = isinstance(flags, list) and any(
            isinstance(flag, str) and flag.upper() == "PRESET" for flag in flags
        )
        if _is_file(folder / "panel-theme.json"):
            kind = "hooandee"
        else:
            kind = "profile" if preset else "third_party"
        name = manifest["name"]
    elif present:
        kind, name = "broken", folder.name
    elif _has_theme_files(folder):
        kind, name = "legacy", folder.name
    elif folder.name.startswith("."):
        # CSS Loader skips it as "not a theme"; hidden folders such as .git are not ours to move.
        return None
    else:
        kind, name = "leftover", folder.name
    return {
        "folder": folder.name,
        "name": name[:_NAME_CHARS],
        "kind": kind,
        "active": _is_active(folder),
    }


def scan(themes_root: str | Path) -> list[dict[str, Any]]:
    root = Path(themes_root)
    try:
        folders = sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return []
    findings = [item for item in map(_classify, folders[:_FOLDER_LIMIT]) if item is not None]
    ours = {item["name"] for item in findings if item["kind"] == "hooandee"}
    for item in findings:
        if item["kind"] != "hooandee" and item["name"] in ours:
            item["kind"] = "duplicate"
    return findings


def summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Counts only: other themes and profiles can carry personal names."""
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        if item["active"]:
            key = "hooandee_active" if item["kind"] == "hooandee" else "other_active"
            counts[key] = counts.get(key, 0) + 1
    return counts


def internal_panel_mode(root: str = "/") -> dict[str, int] | None:
    """Preferred mode of the built-in screen, as the kernel lists it first in `modes`."""
    for connector in sorted(glob.glob(os.path.join(root, "sys/class/drm/card*-*"))):
        name = os.path.basename(connector).split("-", 1)[1]
        if not name.startswith(_INTERNAL_CONNECTORS):
            continue
        try:
            with open(os.path.join(connector, "status"), encoding="ascii") as stream:
                if stream.read().strip() != "connected":
                    continue
            with open(os.path.join(connector, "modes"), encoding="ascii") as stream:
                first = stream.readline().strip()
        except (OSError, UnicodeDecodeError):
            continue
        width, _, height = first.partition("x")
        if width.isdigit() and height.isdigit():
            return {"width": int(width), "height": int(height)}
    return None


def _cleanup_root(themes_root: Path) -> Path:
    return themes_root.parent / CLEANUP_DIRECTORY


def _load_record(directory: Path) -> dict[str, Any] | None:
    """The stored record, an empty one when there is none, or None when it is damaged."""
    try:
        value = json.loads((directory / _RECORD).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": _RECORD_SCHEMA, "moved": [], "disabled": []}
    except (OSError, ValueError):
        return None
    valid = (
        isinstance(value, dict)
        and value.get("schema") == _RECORD_SCHEMA
        and isinstance(value.get("moved"), list)
        and isinstance(value.get("disabled"), list)
        and all(
            isinstance(entry, dict)
            and isinstance(entry.get("folder"), str)
            and isinstance(entry.get("stored"), str)
            for entry in value["moved"]
        )
        and all(isinstance(name, str) for name in value["disabled"])
    )
    return value if valid else None


def _stored_names(directory: Path) -> list[str]:
    return sorted(
        entry.name for entry in directory.iterdir()
        if entry.name not in {_RECORD, _DAMAGED_RECORD} and not entry.name.startswith(f".{_RECORD}")
    )


def _read_record(directory: Path) -> dict[str, Any]:
    """Under the mutation lock. A damaged record is rebuilt from what is stored, so nothing set
    aside becomes unreachable."""
    record = _load_record(directory)
    if record is not None:
        return record
    try:
        os.replace(directory / _RECORD, directory / _DAMAGED_RECORD)
        stored = _stored_names(directory)
    except OSError as error:
        raise ThemeHealthError("invalid_record", "Theme cleanup record is unreadable") from error
    record = {
        "schema": _RECORD_SCHEMA,
        "moved": [{"folder": name, "stored": name, "kind": "unknown"} for name in stored],
        "disabled": [],
    }
    _write_record(directory, record)
    return record


def _write_record(directory: Path, record: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{_RECORD}.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    theme_packages.durable_replace(temporary, directory / _RECORD)


def _settle_record(directory: Path, record: dict[str, Any]) -> None:
    if record["moved"] or record["disabled"]:
        _write_record(directory, record)
        return
    try:
        (directory / _RECORD).unlink(missing_ok=True)
        (directory / _DAMAGED_RECORD).unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        pass


def undo_state(themes_root: str | Path) -> dict[str, Any]:
    directory = _cleanup_root(Path(themes_root))
    record = _load_record(directory)
    if record is None:
        try:
            moved = len(_stored_names(directory))
        except OSError:
            moved = 0
        return {"available": moved > 0, "moved": moved, "disabled": 0, "damaged": True}
    moved, disabled = len(record["moved"]), len(record["disabled"])
    return {"available": bool(moved or disabled), "moved": moved, "disabled": disabled}


def _safe_folder_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and 0 < len(name) <= 255
        and name not in {".", ".."}
        and "/" not in name
        and "\0" not in name
    )


def set_aside(themes_root: str | Path, disabled: list[str]) -> dict[str, Any]:
    """Records the themes the caller is about to disable, then moves every folder whose kind is
    in SET_ASIDE_KINDS out of the CSS Loader themes folder. The kinds come from a fresh scan,
    never from the caller. Each move is recorded before it happens."""
    root = Path(themes_root)
    if not isinstance(disabled, list) or not all(
        isinstance(name, str) and 0 < len(name) <= _NAME_CHARS for name in disabled
    ):
        raise ThemeHealthError("invalid_request", "Disabled theme names are invalid")
    directory = _cleanup_root(root)
    with theme_packages.theme_mutation_lock(root):
        candidates = [item for item in scan(root) if item["kind"] in SET_ASIDE_KINDS]
        if not disabled and not candidates:
            return {"moved": [], "failed": []}
        record = _read_record(directory)
        record["disabled"] = list(dict.fromkeys([*record["disabled"], *disabled]))
        _write_record(directory, record)
        moved: list[str] = []
        failed: list[str] = []
        for item in candidates:
            stored = item["folder"]
            suffix = 1
            while os.path.lexists(directory / stored) or stored in {_RECORD, _DAMAGED_RECORD}:
                stored = f"{item['folder']}.{suffix}"
                suffix += 1
            entry = {"folder": item["folder"], "stored": stored, "kind": item["kind"]}
            record["moved"].append(entry)
            _write_record(directory, record)
            try:
                theme_packages.durable_replace(root / item["folder"], directory / stored)
            except OSError:
                record["moved"].remove(entry)
                _write_record(directory, record)
                failed.append(item["folder"])
                continue
            moved.append(item["folder"])
    return {"moved": moved, "failed": failed}


def restore(themes_root: str | Path) -> dict[str, Any]:
    """Moves set-aside folders back and returns the theme names to enable again; those stay
    recorded until forget_reenabled confirms them. A folder whose original name is taken again
    stays set aside and is reported."""
    root = Path(themes_root)
    directory = _cleanup_root(root)
    with theme_packages.theme_mutation_lock(root):
        record = _read_record(directory)
        restored: list[str] = []
        for entry in list(record["moved"]):
            folder, stored = entry["folder"], entry["stored"]
            if (
                not _safe_folder_name(folder)
                or not _safe_folder_name(stored)
                or stored in {_RECORD, _DAMAGED_RECORD}
            ):
                continue
            source, destination = directory / stored, root / folder
            if not os.path.lexists(source):
                # Moved back before an interruption, or removed by hand: nothing left to restore.
                record["moved"].remove(entry)
                _write_record(directory, record)
                continue
            if os.path.lexists(destination):
                continue
            try:
                theme_packages.durable_replace(source, destination)
            except OSError:
                continue
            record["moved"].remove(entry)
            _write_record(directory, record)
            restored.append(folder)
        kept = [entry["folder"] for entry in record["moved"]]
        reenable = list(record["disabled"])
        _settle_record(directory, record)
    return {"restored": restored, "kept": kept, "reenable": reenable}


def forget_reenabled(themes_root: str | Path) -> None:
    root = Path(themes_root)
    directory = _cleanup_root(root)
    with theme_packages.theme_mutation_lock(root):
        record = _read_record(directory)
        record["disabled"] = []
        _settle_record(directory, record)
