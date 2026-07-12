import json

from json_store import atomic_json_save
from display.const import NATIVE as _NATIVE
from display.const import CALIBRATION as _CALIBRATION

# Contrast is floored at -60 and each gain at 50 so a mis-drag can never crush the panel
# to an unreadable grey/black. Every field in NATIVE must have a range here.
_RANGES = {
    "saturation": (0, 200),
    "temperature": (-100, 100),
    "contrast": (-60, 60),
    "gamma": (-100, 100),
    "hue": (-100, 100),
    "black": (-100, 100),
    "gain_r": (50, 150),
    "gain_g": (50, 150),
    "gain_b": (50, 150),
    "vibrance": (-100, 100),
}

# A missing range would KeyError out of the synchronous _init (hanging the panel);
# fail loudly at import instead.
_missing = set(_NATIVE) - set(_RANGES)
if _missing:
    raise RuntimeError(f"color fields without a range: {sorted(_missing)}")


def _clamp(field, value):
    lo, hi = _RANGES[field]
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return _NATIVE[field]


def sanitize_calibration(fields):
    """Clamp a calibration patch to the safe ranges — the one definition of "safe",
    used by both the live preview and the saved value. Returns only known calibration
    fields, as clamped ints."""
    if not isinstance(fields, dict):
        return {}
    return {f: _clamp(f, fields[f]) for f in _CALIBRATION if f in fields}


class ColorStore:
    """Panel color settings, persisted atomically. HYBRID scope: `saturation` is
    per-game (global + per-appid override, inheriting global); the calibration fields
    (everything else — temperature/contrast/gamma/hue/gains/vibrance) are panel-level
    → GLOBAL only. Never raises on load.

    effective(appid) = calibration always from global, saturation from the game
    override if present else global.
    """

    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        return {f: _clamp(f, raw.get(f, _NATIVE[f])) for f in _NATIVE}

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        games = {}
        for appid, prof in (raw.get("games") or {}).items():
            if isinstance(prof, dict) and "saturation" in prof:
                games[str(appid)] = {"saturation": _clamp("saturation", prof["saturation"])}
        return {"global": self._clean_global(raw.get("global")), "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def effective(self, appid):
        eff = dict(self._data["global"])
        game = self._data["games"].get(str(appid)) if appid is not None else None
        if game is not None:
            eff["saturation"] = game["saturation"]
        return eff

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def set_saturation(self, scope, value, appid=None):
        v = _clamp("saturation", value)
        if scope == "global":
            self._data["global"]["saturation"] = v
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            self._data["games"][str(appid)] = {"saturation": v}
        else:
            raise ValueError(f"unknown scope: {scope}")
        self._save()

    def set_calibration(self, **fields):
        for f in _CALIBRATION:
            if f in fields:
                self._data["global"][f] = _clamp(f, fields[f])
        self._save()

    def apply_preset(self, preset):
        """Overwrite the global profile from a preset dict (per-model OLED look):
        calibration + a global saturation, in one write. Missing fields → native."""
        self._data["global"] = self._clean_global(preset)
        self._save()

    def reset(self):
        """Back to the panel's native look: native global + no game overrides."""
        self._data = {"global": dict(_NATIVE), "games": {}}
        self._save()
