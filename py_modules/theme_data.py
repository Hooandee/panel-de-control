"""Per-theme data that a theme runtime saves through Panel (layouts, folders, preferences).

Each theme gets one JSON file under Panel's settings, outside the theme's own folder, so it survives
updates, reinstalls and uninstalls until the user resets it from Panel.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1
MAX_VALUE_BYTES = 256 * 1024
MAX_SUMMARY_CHARS = 120
MAX_DEPTH = 32
FOLDER_NAME = "theme-data"
_SAFE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MAX_ID_CHARS = 64
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ThemeDataError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _catalog_id(value: object) -> str:
    if not isinstance(value, str) or len(value) > _MAX_ID_CHARS or _SAFE_ID.fullmatch(value) is None:
        raise ThemeDataError("invalid_catalog")
    return value


def _summary(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_SUMMARY_CHARS or _CONTROL.search(value):
        raise ThemeDataError("invalid_summary")
    return value


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ThemeDataError("invalid_value")
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def _encode_value(value: object) -> str:
    _check_depth(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ThemeDataError("invalid_value") from None
    if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ThemeDataError("too_large")
    return encoded


def _folder(settings_dir: Path) -> Path:
    return Path(settings_dir) / FOLDER_NAME


def _path(settings_dir: Path, catalog_id: str) -> Path:
    return _folder(settings_dir) / f"{catalog_id}.json"


def _load(path: Path, catalog_id: str) -> dict | None:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(stored, dict)
        or stored.get("schemaVersion") != SCHEMA_VERSION
        or stored.get("catalogId") != catalog_id
        or not isinstance(stored.get("summary"), str)
        or not isinstance(stored.get("updatedAt"), (int, float))
        or "value" not in stored
    ):
        return None
    return {
        "summary": stored["summary"],
        "value": stored["value"],
        "updatedAt": stored["updatedAt"],
        "bytes": path.stat().st_size,
    }


def read(settings_dir: Path, catalog_id: object) -> dict | None:
    catalog = _catalog_id(catalog_id)
    return _load(_path(settings_dir, catalog), catalog)


def write(settings_dir: Path, catalog_id: object, summary: object, value: object, *, now: float) -> dict:
    catalog = _catalog_id(catalog_id)
    text = _summary(summary)
    encoded = _encode_value(value)
    updated_at = int(now) if math.isfinite(now) else 0
    document = (
        f'{{"schemaVersion":{SCHEMA_VERSION},"catalogId":{json.dumps(catalog)},'
        f'"summary":{json.dumps(text, ensure_ascii=False)},"updatedAt":{updated_at},"value":{encoded}}}'
    )
    folder = _folder(settings_dir)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = _path(settings_dir, catalog)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{catalog}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    try:
        directory = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        pass
    record = _load(target, catalog)
    if record is None:
        raise ThemeDataError("write_failed")
    return record


def list_records(settings_dir: Path) -> list[dict]:
    folder = _folder(settings_dir)
    if not folder.is_dir():
        return []
    records = []
    for path in sorted(folder.glob("*.json")):
        catalog = path.stem
        if _SAFE_ID.fullmatch(catalog) is None:
            continue
        record = _load(path, catalog)
        if record is None:
            continue
        records.append({
            "catalogId": catalog,
            "summary": record["summary"],
            "updatedAt": record["updatedAt"],
            "bytes": record["bytes"],
        })
    return records


def delete(settings_dir: Path, catalog_id: object) -> bool:
    catalog = _catalog_id(catalog_id)
    try:
        _path(settings_dir, catalog).unlink()
    except FileNotFoundError:
        return False
    return True
