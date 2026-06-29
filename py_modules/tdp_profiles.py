import json

from json_store import atomic_json_save


class ProfileStore:
    """Global TDP profile + per-appid overrides, persisted atomically as JSON.
    Each profile stores three power levels: pl1 (sustained), pl2 (slow boost), pl3 (fast boost).
    Migrates the old single-value {"watts": w} shape to {pl1:w, pl2:w, pl3:w}."""

    def __init__(self, path, default_watts):
        self._path = path
        self._default = int(default_watts)
        self._data = self._load()

    def _flat(self, w):
        w = int(w)
        return {"pl1": w, "pl2": w, "pl3": w}

    def _clean(self, raw):
        if not isinstance(raw, dict):
            return self._flat(self._default)
        if "pl1" in raw:
            p1 = int(raw.get("pl1", self._default))
            return {
                "pl1": p1,
                "pl2": int(raw.get("pl2", p1)),
                "pl3": int(raw.get("pl3", p1)),
            }
        if "watts" in raw:  # migrate old shape
            return self._flat(raw["watts"])
        return self._flat(self._default)

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        glob = self._clean(raw.get("global"))
        games = {}
        for appid, prof in (raw.get("games") or {}).items():
            games[str(appid)] = self._clean(prof)
        return {"global": glob, "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def effective(self, appid):
        if appid is not None and str(appid) in self._data["games"]:
            prof = self._data["games"][str(appid)]
        else:
            prof = self._data["global"]
        return {**prof, "watts": prof["pl1"]}  # 'watts' alias = pl1 for simple-mode callers

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def list_games(self):
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = dict(self._data["global"])
        self._save()

    def _store(self, scope, profile, appid):
        if scope == "global":
            self._data["global"] = profile
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            self._data["games"][str(appid)] = profile
        else:
            raise ValueError(f"unknown scope: {scope}")
        self._save()

    def set_levels(self, scope, pl1, pl2, pl3, appid=None):
        self._store(scope, {"pl1": int(pl1), "pl2": int(pl2), "pl3": int(pl3)}, appid)

    def set_watts(self, scope, watts, appid=None):
        self._store(scope, self._flat(watts), appid)
