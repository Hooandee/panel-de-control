from scoped_store import ScopedProfileStore

# Auto-mode boost derivation (single source of truth). When off2/off3 are None the
# rails are derived from PL1: PL2 = 1.2x, PL3 = 1.4x (matches historical behavior).
_AUTO_PL2_RATIO = 1.2
_AUTO_PL3_RATIO = 1.4


def _derive(pl1):
    return round(pl1 * _AUTO_PL2_RATIO), round(pl1 * _AUTO_PL3_RATIO)


class ProfileStore(ScopedProfileStore):
    """Global TDP profile + per-appid overrides. See ScopedProfileStore for the scope
    contract.

    A profile is {pl1, off2, off3}: pl1 is sustained watts; off2/off3 are the boost
    MARGINS stacked above (SPPT = pl1 + off2, FPPT = SPPT + off3). off2/off3 == None
    means AUTO (derived from pl1). Storing margins (not absolute watts) keeps the user's
    intent intact when pl1 moves and a rail clamps at the hardware ceiling (no bounce).
    Also carries per-scope auto_tdp + gpu clock. Migrates the old {"watts": w} and flat
    {pl1,pl2,pl3} shapes."""

    def __init__(self, path, default_watts):
        self._default = int(default_watts)
        super().__init__(path)

    def _auto(self, w):
        return {"pl1": int(w), "off2": None, "off3": None}

    def _clean_global(self, raw):
        base = self._clean_values(raw)
        if isinstance(raw, dict):
            if raw.get("auto_tdp"):
                base["auto_tdp"] = True
            g = raw.get("gpu")
            if isinstance(g, dict):
                base["gpu"] = {"manual": bool(g.get("manual")),
                               "min": g.get("min"), "max": g.get("max")}
        return base

    def _clean_values(self, raw):
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

    # Auto-TDP and GPU-clock are part of the Potencia profile: per-scope, gated by the
    # same follow_global as the TDP value (one tab governs the whole section).
    def auto_tdp(self, appid):
        return bool(self._effective_prof(appid).get("auto_tdp", False))

    def set_auto_tdp(self, scope, enabled, appid=None):
        self._target(scope, appid)["auto_tdp"] = bool(enabled)
        self._save()

    def gpu_clock(self, appid):
        g = self._effective_prof(appid).get("gpu")
        return dict(g) if g else {"manual": False, "min": None, "max": None}

    def set_gpu_clock(self, scope, manual, gmin, gmax, appid=None):
        self._target(scope, appid)["gpu"] = {"manual": bool(manual),
                                              "min": int(gmin), "max": int(gmax)}
        self._save()

    def effective(self, appid):
        prof = self._effective_prof(appid)
        pl1 = prof["pl1"]
        auto = prof["off2"] is None
        if auto:
            pl2, pl3 = _derive(pl1)
        else:
            pl2 = pl1 + prof["off2"]
            pl3 = pl2 + prof["off3"]
        return {"pl1": pl1, "pl2": pl2, "pl3": pl3, "watts": pl1, "auto": auto}

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
