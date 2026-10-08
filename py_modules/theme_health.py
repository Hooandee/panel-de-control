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
_RECORD_SCHEMA = 1
_FOLDER_LIMIT = 200
_MANIFEST_BYTES = 256 * 1024
_NAME_CHARS = 120
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
    if not path.is_file():
        return None, False
    try:
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


def _classify(folder: Path) -> dict[str, Any]:
    manifest, present = _read_manifest(folder / "theme.json")
    if manifest is not None:
        flags = manifest.get("flags")
        preset = isinstance(flags, list) and any(
            isinstance(flag, str) and flag.upper() == "PRESET" for flag in flags
        )
        if (folder / "panel-theme.json").is_file():
            kind = "hooandee"
        else:
            kind = "profile" if preset else "third_party"
        name = manifest["name"]
    elif present:
        kind, name = "broken", folder.name
    elif (folder / "theme.css").is_file() or any((folder / item).is_file() for item in _SFP_FILES):
        kind, name = "legacy", folder.name
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
    findings = [_classify(folder) for folder in folders[:_FOLDER_LIMIT]]
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
        if item["active"] and item["kind"] != "hooandee":
            counts["other_active"] = counts.get("other_active", 0) + 1
        if item["active"] and item["kind"] == "hooandee":
            counts["hooandee_active"] = counts.get("hooandee_active", 0) + 1
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


def _read_record(directory: Path) -> dict[str, Any]:
    try:
        value = json.loads((directory / _RECORD).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": _RECORD_SCHEMA, "moved": [], "disabled": []}
    except (OSError, ValueError) as error:
        raise ThemeHealthError("invalid_record", "Theme cleanup record is unreadable") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != _RECORD_SCHEMA
        or not isinstance(value.get("moved"), list)
        or not isinstance(value.get("disabled"), list)
        or not all(
            isinstance(entry, dict)
            and isinstance(entry.get("folder"), str)
            and isinstance(entry.get("stored"), str)
            for entry in value["moved"]
        )
        or not all(isinstance(name, str) for name in value["disabled"])
    ):
        raise ThemeHealthError("invalid_record", "Theme cleanup record is invalid")
    return value


def _write_record(directory: Path, record: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{_RECORD}.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    theme_packages.durable_replace(temporary, directory / _RECORD)


def undo_state(themes_root: str | Path) -> dict[str, Any]:
    try:
        record = _read_record(_cleanup_root(Path(themes_root)))
    except ThemeHealthError:
        return {"available": False, "moved": 0, "disabled": 0, "error": "invalid_record"}
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
    never from the caller."""
    root = Path(themes_root)
    if not isinstance(disabled, list) or not all(
        isinstance(name, str) and 0 < len(name) <= _NAME_CHARS for name in disabled
    ):
        raise ThemeHealthError("invalid_request", "Disabled theme names are invalid")
    directory = _cleanup_root(root)
    with theme_packages.theme_mutation_lock(root):
        record = _read_record(directory)
        record["disabled"] = list(dict.fromkeys([*record["disabled"], *disabled]))
        _write_record(directory, record)
        moved: list[str] = []
        failed: list[str] = []
        for item in scan(root):
            if item["kind"] not in SET_ASIDE_KINDS:
                continue
            source = root / item["folder"]
            stored = item["folder"]
            suffix = 1
            while (directory / stored).exists() or stored == _RECORD:
                stored = f"{item['folder']}.{suffix}"
                suffix += 1
            try:
                theme_packages.durable_replace(source, directory / stored)
            except OSError:
                failed.append(item["folder"])
                continue
            record["moved"].append({"folder": item["folder"], "stored": stored, "kind": item["kind"]})
            _write_record(directory, record)
            moved.append(item["folder"])
    return {"moved": moved, "failed": failed}


def restore(themes_root: str | Path) -> dict[str, Any]:
    """Moves set-aside folders back and returns the theme names to enable again. Folders whose
    original name is taken again stay set aside and are reported."""
    root = Path(themes_root)
    directory = _cleanup_root(root)
    with theme_packages.theme_mutation_lock(root):
        record = _read_record(directory)
        restored: list[str] = []
        kept: list[dict[str, Any]] = []
        for entry in record["moved"]:
            folder, stored = entry["folder"], entry["stored"]
            source = directory / stored
            destination = root / folder
            if (
                not _safe_folder_name(folder)
                or not _safe_folder_name(stored)
                or stored == _RECORD
                or not source.is_dir()
                or destination.exists()
            ):
                kept.append(entry)
                continue
            try:
                theme_packages.durable_replace(source, destination)
            except OSError:
                kept.append(entry)
                continue
            restored.append(folder)
        reenable = record["disabled"]
        if kept:
            _write_record(directory, {**record, "moved": kept, "disabled": []})
        else:
            try:
                (directory / _RECORD).unlink()
                directory.rmdir()
            except OSError:
                pass
    return {
        "restored": restored,
        "kept": [entry["folder"] for entry in kept],
        "reenable": reenable,
    }
