import json
import os


class ProfileStore:
    """Global TDP profile + per-appid overrides, persisted atomically as JSON.
    Effective(appid) = game profile if present else global. New game copies global."""

    def __init__(self, path, default_watts):
        self._path = path
        self._default = {"watts": int(default_watts)}
        self._data = self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        glob = raw.get("global") or dict(self._default)
        games = raw.get("games") or {}
        # keep only the known {"watts": int} shape
        glob = {"watts": int(glob.get("watts", self._default["watts"]))}
        clean_games = {}
        for appid, prof in games.items():
            if isinstance(prof, dict) and "watts" in prof:
                clean_games[str(appid)] = {"watts": int(prof["watts"])}
        return {"global": glob, "games": clean_games}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f)
        os.replace(tmp, self._path)

    def effective(self, appid):
        if appid is not None and str(appid) in self._data["games"]:
            return dict(self._data["games"][str(appid)])
        return dict(self._data["global"])

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def list_games(self):
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = dict(self._data["global"])
        self._save()

    def set_watts(self, scope, watts, appid=None):
        watts = int(watts)
        if scope == "global":
            self._data["global"] = {"watts": watts}
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            self._data["games"][str(appid)] = {"watts": watts}
        else:
            raise ValueError(f"unknown scope: {scope}")
        self._save()
