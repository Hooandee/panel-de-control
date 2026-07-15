"""Named, reusable EQ curves the user saves and applies to any game/output. A flat global
library keyed by name (saving an existing name overwrites it). Separate from the per-game
EqStore — these are portable presets the user builds, not per-scope state."""
import json

from json_store import atomic_json_save

from audio.const import clamp_gain

_MAX_NAME = 40


def _clean(raw):
    raw = raw if isinstance(raw, dict) else {}
    gains = raw.get("gains")
    if not isinstance(gains, list) or len(gains) != 10:
        gains = [0.0] * 10
    gains = [clamp_gain(g) for g in gains]
    try:
        bass = max(0, min(100, int(raw.get("bass", 0))))
    except (TypeError, ValueError):
        bass = 0
    return {"gains": gains, "bass": bass}


class AudioProfileStore:
    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return {k: _clean(v) for k, v in raw.items() if isinstance(k, str)}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def list(self):
        return [
            {"name": n, "gains": list(s["gains"]), "bass": s["bass"]}
            for n, s in sorted(self._data.items())
        ]

    def save(self, name, gains, bass):
        name = (name or "").strip()[:_MAX_NAME]
        if not name:
            return
        self._data[name] = _clean({"gains": gains, "bass": bass})
        self._save()

    def get(self, name):
        s = self._data.get(name)
        return {"gains": list(s["gains"]), "bass": s["bass"]} if s else None

    def delete(self, name):
        if name in self._data:
            del self._data[name]
            self._save()
