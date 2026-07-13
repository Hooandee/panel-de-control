import json

from json_store import atomic_json_save

_DEFAULTS = {"smt": True, "boost": True, "cores": None}


class CpuProfileStore:
    """Per-game CPU controls (SMT / boost / active cores): global + per-appid overrides
    with a per-game `follow_global` toggle. Mirrors ProfileStore — switching a game to
    follow global keeps its own values (never deletes). Never raises on load."""

    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _default(self):
        return dict(_DEFAULTS)

    def _clean(self, raw):
        base = self._default()
        if isinstance(raw, dict):
            if isinstance(raw.get("smt"), bool):
                base["smt"] = raw["smt"]
            if isinstance(raw.get("boost"), bool):
                base["boost"] = raw["boost"]
            base["cores"] = int(raw["cores"]) if isinstance(raw.get("cores"), int) else None
            if raw.get("follow_global"):
                base["follow_global"] = True
        return base

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        games = {str(a): self._clean(p) for a, p in (raw.get("games") or {}).items()}
        return {"global": self._clean(raw.get("global")), "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def is_following_global(self, appid):
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
        return {"smt": bool(e.get("smt", True)),
                "boost": bool(e.get("boost", True)),
                "cores": e.get("cores")}

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = {k: v for k, v in self._data["global"].items()
                                           if k != "follow_global"}
        self._save()

    def _target(self, scope, appid):
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            prof = self._data["games"].setdefault(
                str(appid), {k: v for k, v in self._data["global"].items() if k != "follow_global"})
            prof["follow_global"] = False  # editing a value activates the game's own profile
            return prof
        raise ValueError(f"unknown scope: {scope}")

    def set_smt(self, scope, enabled, appid=None):
        self._target(scope, appid)["smt"] = bool(enabled)
        self._save()

    def set_boost(self, scope, enabled, appid=None):
        self._target(scope, appid)["boost"] = bool(enabled)
        self._save()

    def set_cores(self, scope, count, appid=None):
        self._target(scope, appid)["cores"] = int(count)
        self._save()
