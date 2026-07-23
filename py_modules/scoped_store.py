"""Shared base for the per-game scoped profile stores (TDP, CPU, color, fan curve).

Each store holds ``{"global": <profile>, "games": {appid: <profile + follow_global>}}``
and shares the same scope contract: a game applies the global profile until it has its
own with ``follow_global`` unset (editing a value activates its own; switching to follow
global keeps the stored values, never deletes). Subclasses supply only their profile
shape (``_clean_global``) and their domain accessors/setters; everything about scopes,
following-global and persistence lives here.

RemapStore (controllers) is intentionally NOT built on this: it nests the per-game
profile one level deeper (``{"overrides": {...}, "follow_global": ...}``) with a bare
global dict, so it keeps its own implementation.
"""
import json

from json_store import atomic_json_save


class ScopedProfileStore:
    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _clean_global(self, raw):
        """Sanitize a raw profile dict into this store's canonical shape (no
        follow_global). Must never raise."""
        raise NotImplementedError

    def _clean_game(self, raw, glob):
        """Sanitize a raw per-game entry. Default = the global shape plus a preserved
        follow_global flag. `glob` is the already-cleaned global (some stores seed from
        it on load). Override for bespoke per-game migration."""
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
        games_raw = raw.get("games")
        if not isinstance(games_raw, dict):  # a list/str/null here would crash .items()
            games_raw = {}
        games = {str(a): self._clean_game(p, glob) for a, p in games_raw.items()}
        return {"global": glob, "games": games}

    def _save(self):
        atomic_json_save(self._path, self._data)

    def is_following_global(self, appid):
        """True when this game applies the global profile: no own profile, or its own is
        toggled to follow global. Own values are never deleted — following just deactivates."""
        g = self._data["games"].get(str(appid)) if appid is not None else None
        return g is None or bool(g.get("follow_global"))

    def set_follow_global(self, appid, follow):
        g = self._data["games"].get(str(appid))
        if g is not None:
            g["follow_global"] = bool(follow)
            self._save()

    def _effective_prof(self, appid):
        """The profile dict a game applies: global when it follows global, else its own."""
        if self.is_following_global(appid):
            return self._data["global"]
        return self._data["games"].get(str(appid), self._data["global"])

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def list_games(self):
        return list(self._data["games"].keys())

    def _new_game_from_global(self):
        """A fresh per-game profile seeded from the current global (global carries no
        follow_global, so the new game entry starts as its own = not following)."""
        return {k: v for k, v in self._data["global"].items() if k != "follow_global"}

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = self._new_game_from_global()
        self._save()

    def game_profile(self, appid):
        """The game's OWN stored profile (what it applies when not following global), or
        None if it has no entry. follow_global is stripped — it's a scope flag, not a
        setting."""
        g = self._data["games"].get(str(appid))
        if g is None:
            return None
        return {k: v for k, v in g.items() if k != "follow_global"}

    def differs_from_global(self, appid):
        """Whether the game has an own stored profile whose values actually differ from
        global. A bare scope-toggle copies global (follow_global=False, same values), so
        it reads as no difference → the overview won't list it as 'configured'."""
        own = self.game_profile(appid)
        if own is None:
            return False
        return own != {k: v for k, v in self._data["global"].items() if k != "follow_global"}

    def forget_game(self, appid):
        """Delete the game's stored profile entirely so it reverts to global. No-op when
        it has none. (The scope tab only DEACTIVATES via follow_global; this is the
        explicit 'reset this game to global' from the overview.)"""
        if str(appid) in self._data["games"]:
            del self._data["games"][str(appid)]
            self._save()

    def _target(self, scope, appid):
        """The profile dict to mutate in place for a scope. Editing a game value seeds it
        from global on first touch and activates its own profile (follow_global=False)."""
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            prof = self._data["games"].setdefault(str(appid), self._new_game_from_global())
            prof["follow_global"] = False
            return prof
        raise ValueError(f"unknown scope: {scope}")

    def _set_profile(self, scope, appid, profile):
        """Replace a scope's whole profile (for stores whose setters rebuild it). A game
        set drops any follow_global key → its own profile is active."""
        if scope == "global":
            self._data["global"] = profile
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            self._data["games"][str(appid)] = profile
        else:
            raise ValueError(f"unknown scope: {scope}")
        self._save()
