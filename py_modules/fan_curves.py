import json

from json_store import atomic_json_save

_VALID = {"auto", "silent", "balanced", "performance", "custom"}


class FanCurveStore:
    """Global fan-curve profile + per-appid overrides, persisted atomically.

    Profile = {"preset": str, "points": list|None}. preset=="auto" => points None
    (firmware control). Otherwise points is an 8-element [[temp,pwm],...] list.
    Default = auto. Mirrors ProfileStore. Never raises on load.
    """

    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _auto(self):
        return {"preset": "auto", "points": None}

    def _clean(self, raw):
        if not isinstance(raw, dict):
            return self._auto()
        preset = raw.get("preset")
        if preset not in _VALID or preset == "auto":
            return self._auto()
        pts = raw.get("points")
        if not isinstance(pts, list) or not pts:
            return self._auto()
        try:
            points = [[int(t), int(p)] for t, p in pts]
        except (TypeError, ValueError):
            return self._auto()
        return {"preset": preset, "points": points}

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        global_profile = self._clean(raw.get("global"))
        games = {}
        for appid, profile in (raw.get("games") or {}).items():
            games[str(appid)] = self._clean(profile)
        return {"global": global_profile, "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def _profile(self, appid):
        if appid is not None and str(appid) in self._data["games"]:
            return self._data["games"][str(appid)]
        return self._data["global"]

    def effective(self, appid):
        return dict(self._profile(appid))

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = dict(self._data["global"])
        self._save()

    def _set(self, scope, appid, profile):
        if scope == "global":
            self._data["global"] = profile
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            self._data["games"][str(appid)] = profile
        else:
            raise ValueError(f"unknown scope: {scope}")
        self._save()

    def set_preset(self, scope, preset_id, points, appid=None):
        self._set(scope, appid, {"preset": preset_id, "points": [list(p) for p in points]})

    def set_custom(self, scope, points, appid=None):
        self._set(scope, appid, {"preset": "custom", "points": [list(p) for p in points]})

    def set_auto(self, scope, appid=None):
        self._set(scope, appid, self._auto())
