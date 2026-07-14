"""Persisted controller-remap overrides, per scope (global + per-game).

Holds ``{global: {source: targets}, games: {appid: {overrides, follow_global}}}``.
A game applies the global overrides until it has its own profile with
follow_global=False (mirrors tdp_profiles.ProfileStore). Switching scope never
deletes either side. JSON, atomic write, robust load (never raises). Migrates the
old flat ``{source: targets}`` shape into ``global``.
"""
import json

from json_store import atomic_json_save


def _clean_overrides(raw) -> dict:
    return {k: v for k, v in raw.items() if isinstance(v, list)} if isinstance(raw, dict) else {}


class RemapStore:
    def __init__(self, path: str):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        return self._coerce(raw)

    def _coerce(self, raw) -> dict:
        if not isinstance(raw, dict):
            return {"global": {}, "games": {}}
        # Old flat shape {source: targets} → migrate into the global scope.
        if "global" not in raw and "games" not in raw:
            return {"global": _clean_overrides(raw), "games": {}}
        games = {}
        for appid, g in (raw.get("games") or {}).items():
            if isinstance(g, dict):
                games[str(appid)] = {
                    "overrides": _clean_overrides(g.get("overrides")),
                    "follow_global": bool(g.get("follow_global")),
                }
        return {"global": _clean_overrides(raw.get("global")), "games": games}

    def _game(self, appid):
        return self._data["games"].get(str(appid)) if appid is not None else None

    def is_following_global(self, appid) -> bool:
        g = self._game(appid)
        return g is None or bool(g.get("follow_global"))

    def set_follow_global(self, appid, follow: bool) -> None:
        g = self._game(appid)
        if g is not None:
            g["follow_global"] = bool(follow)
            self._save()

    def effective_overrides(self, appid) -> dict:
        """The overrides that actually apply for the running game (global when it
        follows global, else its own). A copy — callers must not mutate the store."""
        if self.is_following_global(appid):
            return dict(self._data["global"])
        return dict(self._game(appid)["overrides"])

    def overrides_for(self, scope: str, appid=None) -> dict:
        """The overrides being viewed/edited in a specific scope. A game with no own
        profile yet shows the global set (the seed it would copy)."""
        if scope == "game" and appid is not None:
            g = self._game(appid)
            return dict(g["overrides"]) if g else dict(self._data["global"])
        return dict(self._data["global"])

    def has_game(self, appid) -> bool:
        return str(appid) in self._data["games"]

    def list_games(self) -> list:
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid) -> None:
        self._data["games"][str(appid)] = {
            "overrides": dict(self._data["global"]),
            "follow_global": False,
        }
        self._save()

    def game_profile(self, appid):
        """The game's OWN stored overrides ({source: targets}), or None if no entry."""
        g = self._game(appid)
        return dict(g["overrides"]) if g is not None else None

    def differs_from_global(self, appid) -> bool:
        """Whether the game's own overrides actually differ from global (a bare
        scope-toggle copies global → not 'configured')."""
        own = self.game_profile(appid)
        return own is not None and own != dict(self._data["global"])

    def forget_game(self, appid) -> None:
        """Delete the game's stored remap so it reverts to global. No-op when none."""
        if str(appid) in self._data["games"]:
            del self._data["games"][str(appid)]
            self._save()

    def _target(self, scope: str, appid=None) -> dict:
        """The overrides dict to mutate for a scope. Editing a game value activates
        its own profile (follow_global=False), seeded from global on first touch."""
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            g = self._data["games"].setdefault(
                str(appid), {"overrides": dict(self._data["global"]), "follow_global": False})
            g["follow_global"] = False
            return g["overrides"]
        raise ValueError(f"unknown scope: {scope}")

    def replace(self, scope: str, appid, data: dict) -> None:
        tgt = self._target(scope, appid)
        tgt.clear()
        tgt.update(data)
        self._save()

    def reset(self, scope: str, appid=None) -> None:
        self._target(scope, appid).clear()
        self._save()

    def _save(self) -> None:
        atomic_json_save(self._path, self._data)
