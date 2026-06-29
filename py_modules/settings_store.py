import json

from json_store import atomic_json_save


class SettingsStore:
    """Atomic JSON persistence. Merges stored values over a DEFAULTS dict so adding
    a new key never breaks an old save, and only known keys are kept."""

    def __init__(self, path):
        self._path = path

    def load(self, defaults):
        try:
            with open(self._path) as handle:
                stored = json.load(handle)
        except (OSError, ValueError):
            return dict(defaults)
        merged = dict(defaults)
        merged.update({k: v for k, v in stored.items() if k in defaults})
        return merged

    def save(self, data):
        atomic_json_save(self._path, data)
