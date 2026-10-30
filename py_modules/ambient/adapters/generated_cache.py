from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from json_store import atomic_json_save

_GENERATED = re.compile(r"(?:optimized/opt-[0-9a-f]{32}\.mp4|[0-9a-f]{64}\.(?:jpg|jpeg|png|webp|gif|mp4|webm|mkv|mov))")


class GeneratedCache:
    def __init__(self, directory: str):
        self.directory = os.path.realpath(directory)
        self.path = os.path.join(directory, "generated.json")
        try:
            with open(self.path, encoding="utf-8") as handle:
                records = json.load(handle)
            self.records = {name: record for name, record in records.items() if self._valid(record)} if isinstance(records, dict) else {}
        except (OSError, ValueError):
            self.records = {}

    @staticmethod
    def _valid(record: Any) -> bool:
        return isinstance(record, dict) and isinstance(record.get("ref"), str) and isinstance(record.get("source"), str) and isinstance(record.get("collections"), list) and all(isinstance(owner, str) for owner in record["collections"]) and isinstance(record.get("managed"), bool)

    def _target(self, name: str) -> str | None:
        if not isinstance(name, str) or not _GENERATED.fullmatch(name):
            return None
        path = os.path.join(self.directory, name)
        if os.path.islink(path) or os.path.commonpath((os.path.realpath(path), self.directory)) != self.directory:
            return None
        return path

    def register(self, path: str, record: dict[str, Any]) -> None:
        name = os.path.relpath(path, self.directory)
        if self._target(name) is None:
            return
        previous = self.records.get(name, {})
        record["collections"] = sorted(set(previous.get("collections", [])) | set(record["collections"]))
        record["managed"] = bool(previous.get("managed") or record["managed"])
        if previous == record:
            return
        updated = {**self.records, name: record}
        atomic_json_save(self.path, updated)
        self.records = updated

    def discard_unregistered(self, path: str) -> None:
        name = os.path.relpath(path, self.directory)
        target = self._target(name)
        if target is not None and name not in self.records:
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass

    def prune(self, referenced: Callable[[dict[str, Any]], bool]) -> list[str]:
        removed = []
        changed = False
        for name, record in list(self.records.items()):
            if record.get("managed") is not True or referenced(record):
                continue
            target = self._target(name)
            if target is None:
                continue
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
            except OSError:
                continue
            removed.append(target)
            del self.records[name]
            changed = True
        if changed:
            atomic_json_save(self.path, self.records)
        return removed
