import json

from json_store import atomic_json_save

# Auto-mode boost derivation (single source of truth). When off2/off3 are None the
# rails are derived from PL1: PL2 = 1.2x, PL3 = 1.4x (matches historical behavior).
_AUTO_PL2_RATIO = 1.2
_AUTO_PL3_RATIO = 1.4


def _derive(pl1):
    return round(pl1 * _AUTO_PL2_RATIO), round(pl1 * _AUTO_PL3_RATIO)


class ProfileStore:
    """Global TDP profile + per-appid overrides, persisted atomically as JSON.

    A profile is {pl1, off2, off3}: pl1 is sustained watts; off2/off3 are the boost
    MARGINS stacked above (SPPT = pl1 + off2, FPPT = SPPT + off3). off2/off3 == None
    means AUTO (derived from pl1). Storing margins (not absolute watts) keeps the user's
    intent intact when pl1 moves and a rail clamps at the hardware ceiling (no bounce).
    Migrates the old {"watts": w} and flat {pl1,pl2,pl3} shapes."""

    def __init__(self, path, default_watts):
        self._path = path
        self._default = int(default_watts)
        self._data = self._load()

    def _auto(self, w):
        return {"pl1": int(w), "off2": None, "off3": None}

    def _clean(self, raw):
        if not isinstance(raw, dict):
            return self._auto(self._default)
        if "off2" in raw or "off3" in raw:  # current shape
            pl1 = int(raw.get("pl1", self._default))
            o2 = raw.get("off2")
            o3 = raw.get("off3")
            if o2 is None or o3 is None:  # invariant: both None (auto) or both int (manual)
                o2 = o3 = None
            else:
                o2 = max(0, int(o2))
                o3 = max(0, int(o3))
            return {"pl1": pl1, "off2": o2, "off3": o3}
        if "pl1" in raw and "pl2" in raw:  # migrate old flat/absolute shape
            pl1 = int(raw["pl1"])
            o2 = max(0, int(raw.get("pl2", pl1)) - pl1)
            o3 = max(0, int(raw.get("pl3", pl1)) - int(raw.get("pl2", pl1)))
            if o2 == 0 and o3 == 0:
                return self._auto(pl1)  # flat -> auto (preserves derived boost)
            return {"pl1": pl1, "off2": o2, "off3": o3}
        if "pl1" in raw:
            return self._auto(int(raw["pl1"]))
        if "watts" in raw:  # migrate oldest shape
            return self._auto(int(raw["watts"]))
        return self._auto(self._default)

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

    def _profile(self, appid):
        if appid is not None and str(appid) in self._data["games"]:
            return self._data["games"][str(appid)]
        return self._data["global"]

    def effective(self, appid):
        prof = self._profile(appid)
        pl1 = prof["pl1"]
        auto = prof["off2"] is None
        if auto:
            pl2, pl3 = _derive(pl1)
        else:
            pl2 = pl1 + prof["off2"]
            pl3 = pl2 + prof["off3"]
        return {"pl1": pl1, "pl2": pl2, "pl3": pl3, "watts": pl1, "auto": auto}

    def has_game(self, appid):
        return str(appid) in self._data["games"]

    def list_games(self):
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid):
        self._data["games"][str(appid)] = dict(self._data["global"])
        self._save()

    def _target(self, scope, appid):
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            prof = self._data["games"].setdefault(str(appid), dict(self._data["global"]))
            return prof
        raise ValueError(f"unknown scope: {scope}")

    def set_pl1(self, scope, pl1, appid=None):
        """Set sustained watts, keeping the auto/manual margin mode intact.

        For a game scope that has no profile yet, creates a fresh auto profile
        (off2/off3=None) rather than copying global — the caller controls margins
        separately via set_offsets / set_levels.
        """
        if scope == "game" and appid is not None and str(appid) not in self._data["games"]:
            self._data["games"][str(appid)] = self._auto(pl1)
        else:
            self._target(scope, appid)["pl1"] = int(pl1)
        self._save()

    def set_offsets(self, scope, off2, off3, appid=None):
        """Switch to manual mode with explicit boost margins."""
        prof = self._target(scope, appid)
        prof["off2"] = max(0, int(off2))
        prof["off3"] = max(0, int(off3))
        self._save()

    def set_auto(self, scope, appid=None):
        """Revert boost rails to auto (derived)."""
        prof = self._target(scope, appid)
        prof["off2"] = None
        prof["off3"] = None
        self._save()

    def set_levels(self, scope, pl1, pl2, pl3, appid=None):
        """Absolute API (back-compat / game copy): converts absolute (pl1, pl2, pl3) to explicit margins (off2=pl2-pl1, off3=pl3-pl2) and stores as manual mode."""
        prof = self._target(scope, appid)
        prof["pl1"] = int(pl1)
        prof["off2"] = max(0, int(pl2) - int(pl1))
        prof["off3"] = max(0, int(pl3) - int(pl2))
        self._save()

