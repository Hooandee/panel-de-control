import json

from json_store import atomic_json_save
from mangohud.config import coerce_model
from scoped_store import ScopedProfileStore


class HudStore(ScopedProfileStore):
    """Persists the HUD model per scope: a global model plus an optional own model per
    game (``follow_global`` decides which one a game applies). Always reads/writes
    through coerce_model so a corrupt or outdated save can never brick the panel.

    Without any per-game model the file stays the flat global model it has always been,
    so users who never touch "Juego" keep the exact same file (and can downgrade)."""

    def _clean_global(self, raw):
        return coerce_model(raw)

    def _load(self):
        raw = self._read_raw()
        if "global" not in raw and "games" not in raw:
            raw = {"global": raw}
        return self._clean_data(raw)

    def _read_raw(self):
        try:
            with open(self._path) as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _clean_data(self, raw):
        glob = self._clean_global(raw.get("global"))
        games_raw = raw.get("games")
        if not isinstance(games_raw, dict):
            games_raw = {}
        return {
            "global": glob,
            "games": {str(a): self._clean_game(p, glob) for a, p in games_raw.items()},
        }

    def _save(self):
        if self._data["games"]:
            atomic_json_save(self._path, self._data)
        else:
            atomic_json_save(self._path, self._data["global"])

    def load(self):
        return dict(self._data["global"])

    def effective(self, appid):
        """The model a game applies: its own, or the global one while it follows global."""
        return {k: v for k, v in self._effective_prof(appid).items() if k != "follow_global"}

    def save(self, model):
        return self.set_model("global", None, model)

    def set_model(self, scope, appid, model):
        clean = coerce_model(model)
        if scope == "game":
            self._set_profile("game", appid, clean)
        else:
            self._set_profile("global", None, clean)
        return dict(clean)

    def set_follow(self, appid, follow):
        """Switch a game between its own model and the global one. Using its own for the
        first time seeds it from global; the stored own model is never deleted."""
        if not follow and not self.has_game(appid):
            self.create_game_from_global(appid)
        self.set_follow_global(appid, follow)

    def own_hud_games(self):
        """Games that currently apply their own model (not following global)."""
        return [a for a in self.list_games() if not self.is_following_global(a)]

    def disable_all(self):
        """Switch the HUD off in every scope (conflict resolved by keeping the external file)."""
        self._data["global"]["enabled"] = False
        for prof in self._data["games"].values():
            prof["enabled"] = False
        self._save()
        return dict(self._data["global"])
