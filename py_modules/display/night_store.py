import json

from json_store import atomic_json_save
from display.night import clamp_minute

# warmth = added temperature units (0..100); window in minutes-of-day (22:00 → 07:00).
# `enabled` is the master; `schedule_enabled` picks scheduled-window vs always-on.
_DEFAULTS = {
    "warmth": 40,
    "enabled": False,
    "schedule_enabled": False,
    "start": 22 * 60,
    "end": 7 * 60,
}


def _clamp_warmth(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return _DEFAULTS["warmth"]


class NightStore:
    """Night-mode settings, persisted atomically. Global (panel-level). Never raises
    on load — a corrupt/partial file falls back to the neutral defaults."""

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
        return {
            "warmth": _clamp_warmth(raw.get("warmth", _DEFAULTS["warmth"])),
            "enabled": bool(raw.get("enabled", False)),
            "schedule_enabled": bool(raw.get("schedule_enabled", False)),
            "start": clamp_minute(raw.get("start", _DEFAULTS["start"])),
            "end": clamp_minute(raw.get("end", _DEFAULTS["end"])),
        }

    def get(self):
        return dict(self._data)

    def set(self, warmth=None, enabled=None, schedule_enabled=None, start=None, end=None):
        if warmth is not None:
            self._data["warmth"] = _clamp_warmth(warmth)
        if enabled is not None:
            self._data["enabled"] = bool(enabled)
        if schedule_enabled is not None:
            self._data["schedule_enabled"] = bool(schedule_enabled)
        if start is not None:
            self._data["start"] = clamp_minute(start)
        if end is not None:
            self._data["end"] = clamp_minute(end)
        atomic_json_save(self._path, self._data)
        return dict(self._data)
