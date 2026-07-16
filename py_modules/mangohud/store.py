import json

from json_store import atomic_json_save
from mangohud.config import coerce_model


class HudStore:
    """Persists the single global HUD model as JSON. Always reads/writes through
    coerce_model so a corrupt or outdated save can never brick the panel."""

    def __init__(self, path):
        self._path = path

    def load(self):
        try:
            with open(self._path) as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            raw = {}
        return coerce_model(raw)

    def save(self, model):
        clean = coerce_model(model)
        atomic_json_save(self._path, clean)
        return clean
