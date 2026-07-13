import json

from json_store import atomic_json_save

# Boost derivation for the "auto" mode (single source of truth): moderate managed
# headroom above PL1, clamped later to each rail's firmware max. SPPT = 1.2x, FPPT = 1.4x.
_AUTO_PL2_RATIO = 1.2
_AUTO_PL3_RATIO = 1.4

# Boost behaviour modes:
#   estable  — SPPT = FPPT = PL1 (flat: "what you set is what it draws"). The DEFAULT.
#   auto     — managed headroom derived from PL1 (see ratios above).
#   custom   — explicit additive margins off2/off3 stacked above PL1.
_MODES = ("estable", "auto", "custom")
_DEFAULT_MODE = "estable"


def _derive(pl1):
    return round(pl1 * _AUTO_PL2_RATIO), round(pl1 * _AUTO_PL3_RATIO)


def _norm_mode(mode):
    return mode if mode in _MODES else _DEFAULT_MODE


class ProfileStore:
    """Global TDP profile + per-appid overrides, persisted atomically as JSON.

    A profile is {pl1, mode, off2, off3}: pl1 is sustained watts; mode picks how the
    boost rails (SPPT/FPPT) relate to pl1 — estable (flat, the default), auto (managed
    1.2x/1.4x headroom) or custom (explicit off2/off3 margins). Storing margins (not
    absolute watts) keeps the user's intent intact when pl1 moves and a rail clamps at
    the hardware ceiling (no bounce). Migrates the old {"watts": w}, flat {pl1,pl2,pl3}
    and off2/off3-shape profiles; the old silent default (derived boost) migrates to
    ESTABLE so a stale install stops over-drawing on the next apply."""

    def __init__(self, path, default_watts):
        self._path = path
        self._default = int(default_watts)
        self._data = self._load()

    def _profile_dict(self, pl1, mode=_DEFAULT_MODE, off2=0, off3=0):
        # off2/off3 coerced None-safe: _clean is the shape-validator and must never
        # raise on a malformed/partial persisted profile (a raise here bricks the panel).
        return {"pl1": int(pl1), "mode": _norm_mode(mode),
                "off2": max(0, int(off2 or 0)), "off3": max(0, int(off3 or 0))}

    def _clean(self, raw):
        if not isinstance(raw, dict):
            return self._profile_dict(self._default)
        if "mode" in raw:  # current shape (_profile_dict normalizes the mode)
            return self._profile_dict(raw.get("pl1", self._default), raw.get("mode"),
                                      raw.get("off2", 0), raw.get("off3", 0))
        if "off2" in raw or "off3" in raw:  # previous shape (None=old auto default)
            pl1 = int(raw.get("pl1", self._default))
            o2, o3 = raw.get("off2"), raw.get("off3")
            if o2 is None or o3 is None:
                # Old auto (silent default derived boost) → migrate to flat.
                return self._profile_dict(pl1, "estable")
            return self._profile_dict(pl1, "custom", o2, o3)
        if "pl1" in raw and "pl2" in raw:  # old absolute shape
            pl1 = int(raw["pl1"])
            o2 = max(0, int(raw.get("pl2", pl1)) - pl1)
            o3 = max(0, int(raw.get("pl3", pl1)) - int(raw.get("pl2", pl1)))
            if o2 == 0 and o3 == 0:
                return self._profile_dict(pl1, "estable")  # truly flat → estable
            return self._profile_dict(pl1, "custom", o2, o3)
        if "pl1" in raw:
            return self._profile_dict(int(raw["pl1"]))
        if "watts" in raw:  # oldest shape → flat
            return self._profile_dict(int(raw["watts"]))
        return self._profile_dict(self._default)

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
        mode = prof.get("mode", _DEFAULT_MODE)
        if mode == "auto":
            pl2, pl3 = _derive(pl1)
        elif mode == "custom":
            pl2 = pl1 + prof["off2"]
            pl3 = pl2 + prof["off3"]
        else:  # estable (flat)
            pl2 = pl3 = pl1
        return {"pl1": pl1, "pl2": pl2, "pl3": pl3, "watts": pl1, "mode": mode}

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
        """Set sustained watts, keeping the boost mode + margins intact.

        For a game scope that has no profile yet, creates a fresh estable profile
        rather than copying global — the caller controls the mode separately.
        """
        if scope == "game" and appid is not None and str(appid) not in self._data["games"]:
            self._data["games"][str(appid)] = self._profile_dict(pl1)
        else:
            self._target(scope, appid)["pl1"] = int(pl1)
        self._save()

    def set_boost_mode(self, scope, mode, appid=None):
        """Set the boost mode (estable/auto/custom). Unknown modes fall back to estable.
        Keeps pl1. When entering custom from auto with no stored margins, seed the
        editable offsets from auto's derived rails so switching doesn't silently drop
        the headroom that was showing (estable has none to preserve → stays flat).
        Stored non-zero custom margins are never overwritten (mode switches round-trip)."""
        prof = self._target(scope, appid)
        mode = _norm_mode(mode)
        if (mode == "custom" and prof["mode"] == "auto"
                and prof["off2"] == 0 and prof["off3"] == 0):
            pl2, pl3 = _derive(prof["pl1"])
            prof["off2"], prof["off3"] = pl2 - prof["pl1"], pl3 - pl2
        prof["mode"] = mode
        self._save()

    def set_offsets(self, scope, off2, off3, appid=None):
        """Switch to custom mode with explicit boost margins."""
        prof = self._target(scope, appid)
        prof["mode"] = "custom"
        prof["off2"] = max(0, int(off2))
        prof["off3"] = max(0, int(off3))
        self._save()

    def set_levels(self, scope, pl1, pl2, pl3, appid=None):
        """Absolute API (back-compat / game copy): converts absolute (pl1, pl2, pl3) to
        explicit margins (off2=pl2-pl1, off3=pl3-pl2) and stores as custom mode."""
        prof = self._target(scope, appid)
        prof["pl1"] = int(pl1)
        prof["mode"] = "custom"
        prof["off2"] = max(0, int(pl2) - int(pl1))
        prof["off3"] = max(0, int(pl3) - int(pl2))
        self._save()
