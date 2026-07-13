from scoped_store import ScopedProfileStore

_DEFAULTS = {"smt": True, "boost": True, "cores": None}


class CpuProfileStore(ScopedProfileStore):
    """Per-game CPU controls (SMT / boost / active cores): global + per-appid overrides
    with a per-game follow_global toggle. See ScopedProfileStore for the scope contract."""

    def _clean_global(self, raw):
        base = dict(_DEFAULTS)
        if isinstance(raw, dict):
            if isinstance(raw.get("smt"), bool):
                base["smt"] = raw["smt"]
            if isinstance(raw.get("boost"), bool):
                base["boost"] = raw["boost"]
            base["cores"] = int(raw["cores"]) if isinstance(raw.get("cores"), int) else None
        return base

    def effective(self, appid):
        e = self._effective_prof(appid)
        return {"smt": bool(e.get("smt", True)),
                "boost": bool(e.get("boost", True)),
                "cores": e.get("cores")}

    def set_smt(self, scope, enabled, appid=None):
        self._target(scope, appid)["smt"] = bool(enabled)
        self._save()

    def set_boost(self, scope, enabled, appid=None):
        self._target(scope, appid)["boost"] = bool(enabled)
        self._save()

    def set_cores(self, scope, count, appid=None):
        self._target(scope, appid)["cores"] = int(count)
        self._save()
