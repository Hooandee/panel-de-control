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
    """Panel color settings, persisted atomically. The WHOLE profile (saturation +
    calibration: temperature/contrast/gamma/hue/gains/vibrance) is per-game: global +
    per-appid override with a `follow_global` toggle (never deletes). Mirrors
    ProfileStore. effective(appid) = the game's own profile, or global when it follows
    global / has none. Never raises on load."""

    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        prof = {f: _clamp(f, raw.get(f, _NATIVE[f])) for f in _NATIVE}
        if raw.get("hdr"):
            prof["hdr"] = True  # HDR on/off is part of the per-scope display profile
        return prof

    def _clean_game(self, raw, glob):
        # Older stores kept ONLY saturation per game (calibration was global). Preserve
        # that intent: keep the global calibration, override just the saturation, so the
        # game doesn't drop to native calibration on load.
        if (isinstance(raw, dict) and "saturation" in raw
                and not raw.get("follow_global")
                and not any(f in raw for f in _CALIBRATION)):
            prof = {k: v for k, v in glob.items() if k != "follow_global"}
            prof["saturation"] = _clamp("saturation", raw["saturation"])
            return prof
        prof = self._clean_global(raw)
        if isinstance(raw, dict) and raw.get("follow_global"):
            prof["follow_global"] = True
        return prof

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        glob = self._clean_global(raw.get("global"))
        games = {}
        for appid, prof in (raw.get("games") or {}).items():
            if isinstance(prof, dict):
                games[str(appid)] = self._clean_game(prof, glob)
        return {"global": glob, "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def is_following_global(self, appid):
        """True when this game applies the global color profile: no own profile, or its
        own is toggled to follow global. Own values are never deleted."""
        g = self._data["games"].get(str(appid)) if appid is not None else None
        return g is None or bool(g.get("follow_global"))

    def set_follow_global(self, appid, follow):
        g = self._data["games"].get(str(appid))
        if g is not None:
            g["follow_global"] = bool(follow)
            self._save()

    def _effective_prof(self, appid):
        if self.is_following_global(appid):
            return self._data["global"]
        return self._data["games"].get(str(appid), self._data["global"])

    def effective(self, appid):
        e = self._effective_prof(appid)
        return {f: e[f] for f in _NATIVE}

    def hdr(self, appid):
        return bool(self._effective_prof(appid).get("hdr", False))

    def set_hdr(self, scope, enabled, appid=None):
        self._target(scope, appid)["hdr"] = bool(enabled)
        self._save()

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def _copy_global(self):
        return {k: v for k, v in self._data["global"].items() if k != "follow_global"}

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = self._copy_global()
        self._save()

    def _target(self, scope, appid):
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            prof = self._data["games"].setdefault(str(appid), self._copy_global())
            prof["follow_global"] = False  # editing a value activates the game's own profile
            return prof
        raise ValueError(f"unknown scope: {scope}")

    def set_saturation(self, scope, value, appid=None):
        self._target(scope, appid)["saturation"] = _clamp("saturation", value)
        self._save()

    def set_calibration(self, scope, appid=None, **fields):
        t = self._target(scope, appid)
        for f in _CALIBRATION:
            if f in fields:
                t[f] = _clamp(f, fields[f])
        self._save()

    def apply_preset(self, scope, preset, appid=None):
        """Overwrite a scope's profile from a preset dict (per-model OLED look): the full
        calibration + saturation in one write. Missing fields → native. HDR is a display
        mode, not part of a look, so the scope's current HDR is kept across the change."""
        prof = self._clean_global(preset)
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            if self.hdr(appid):
                prof["hdr"] = True  # keep the game's effective HDR
            self._data["games"][str(appid)] = prof  # replaces → own active (no follow_global)
        else:
            if self._data["global"].get("hdr"):
                prof["hdr"] = True
            self._data["global"] = prof
        self._save()

    def reset(self):
        """Back to the panel's native look: native global + no game overrides. HDR is a
        display mode, not a look, so it survives a color reset (kept from global)."""
        glob = dict(_NATIVE)
        if self._data["global"].get("hdr"):
            glob["hdr"] = True
        self._data = {"global": glob, "games": {}}
        self._save()
