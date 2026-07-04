"""Persisted controller-remap overrides (global — InputPlumber profiles are global).

Maps a source button -> its user-chosen target list. Missing buttons fall back to
the device default. JSON, atomic write, robust load (never raises)."""
import json

from json_store import atomic_json_save


class RemapStore:
    def __init__(self, path: str):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def all(self) -> dict:
        return dict(self._data)

    def set(self, source: str, targets: list) -> None:
        self._data[source] = targets
        self._save()

    def clear(self, source: str) -> None:
        self._data.pop(source, None)
        self._save()

    def replace(self, data: dict) -> None:
        self._data = dict(data)
        self._save()

    def reset(self) -> None:
        self._data = {}
        self._save()

    def _save(self) -> None:
        atomic_json_save(self._path, self._data)
