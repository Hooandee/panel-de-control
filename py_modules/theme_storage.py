"""Durable key/value storage for theme runtimes, one file per catalog id.

CEF's localStorage does not reliably survive a reboot or a power cut, so a runtime that keeps
user layout there loses it. This store writes through fsync (file and directory) before it
reports success, and a read that cannot be completed raises instead of answering "no value".
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path

SCHEMA_VERSION = 1
MAX_KEYS = 64
MAX_VALUE_BYTES = 128 * 1024
MAX_THEME_BYTES = 512 * 1024
MAX_THEMES = 32

_SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ThemeStorageError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require_id(catalog_id: object) -> str:
    if not isinstance(catalog_id, str) or len(catalog_id) > 64 or _SAFE_ID.fullmatch(catalog_id) is None:
        raise ThemeStorageError("invalid_theme")
    return catalog_id


def _require_key(key: object) -> str:
    if not isinstance(key, str) or _SAFE_KEY.fullmatch(key) is None:
        raise ThemeStorageError("invalid_key")
    return key


def _encoded_size(values: dict[str, str]) -> int:
    return len(json.dumps({"schemaVersion": SCHEMA_VERSION, "values": values}).encode("utf-8"))


class ThemeStorage:
    def __init__(self, root: str | os.PathLike[str]):
        self._root = Path(root)
        self._lock = threading.Lock()

    def _path(self, catalog_id: str) -> Path:
        return self._root / f"{catalog_id}.json"

    def _read(self, catalog_id: str) -> dict[str, str]:
        path = self._path(catalog_id)
        if self._root.is_symlink() or path.is_symlink():
            raise ThemeStorageError("unsafe_path")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError:
            raise ThemeStorageError("read_failed") from None
        if len(raw) > MAX_THEME_BYTES + 4096:
            raise ThemeStorageError("corrupt")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ThemeStorageError("corrupt") from None
        values = document.get("values") if isinstance(document, dict) else None
        if (
            not isinstance(values, dict)
            or document.get("schemaVersion") != SCHEMA_VERSION
            or not all(
                isinstance(key, str) and _SAFE_KEY.fullmatch(key) and isinstance(value, str)
                for key, value in values.items()
            )
        ):
            raise ThemeStorageError("corrupt")
        return values

    def _write(self, catalog_id: str, values: dict[str, str]) -> None:
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self._root.is_symlink():
            raise ThemeStorageError("unsafe_path")
        path = self._path(catalog_id)
        fd, temporary = tempfile.mkstemp(prefix=f".{catalog_id}.", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"schemaVersion": SCHEMA_VERSION, "values": values}, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            raise ThemeStorageError("write_failed") from None
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def get(self, catalog_id: str, key: str) -> str | None:
        catalog_id = _require_id(catalog_id)
        key = _require_key(key)
        with self._lock:
            return self._read(catalog_id).get(key)

    def set(self, catalog_id: str, key: str, value: object) -> None:
        catalog_id = _require_id(catalog_id)
        key = _require_key(key)
        if not isinstance(value, str) or "\0" in value:
            raise ThemeStorageError("invalid_value")
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise ThemeStorageError("too_large")
        with self._lock:
            path = self._path(catalog_id)
            try:
                values = self._read(catalog_id)
            except ThemeStorageError as error:
                if error.code != "corrupt":
                    raise
                # A damaged file is kept beside the fresh one for support instead of blocking every later save.
                try:
                    os.replace(path, path.with_suffix(".json.corrupt"))
                except OSError:
                    raise ThemeStorageError("write_failed") from None
                values = {}
            if values.get(key) == value:
                return
            if not path.exists() and self._theme_count() >= MAX_THEMES:
                raise ThemeStorageError("too_many_themes")
            if key not in values and len(values) >= MAX_KEYS:
                raise ThemeStorageError("too_many_keys")
            values = {**values, key: value}
            if _encoded_size(values) > MAX_THEME_BYTES:
                raise ThemeStorageError("too_large")
            self._write(catalog_id, values)

    def _theme_count(self) -> int:
        try:
            return sum(1 for entry in self._root.glob("*.json") if _SAFE_ID.fullmatch(entry.stem))
        except OSError:
            return 0

    def summary(self) -> list[dict[str, object]]:
        """Identity, key count and size per theme for support; never the values."""
        result: list[dict[str, object]] = []
        with self._lock:
            try:
                entries = sorted(self._root.glob("*.json"))
            except OSError:
                return result
            for entry in entries:
                if _SAFE_ID.fullmatch(entry.stem) is None:
                    continue
                try:
                    keys = sorted(self._read(entry.stem))
                    result.append({"catalogId": entry.stem, "keys": keys, "bytes": entry.stat().st_size})
                except (ThemeStorageError, OSError) as error:
                    result.append({"catalogId": entry.stem, "error": getattr(error, "code", "read_failed")})
        return result
