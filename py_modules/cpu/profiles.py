from scoped_store import ScopedProfileStore

_AUTO_FREQUENCY = {"manual": False, "min_khz": None, "max_khz": None}
_DEFAULTS = {
    "smt": True,
    "boost": True,
    "cores": None,
    "frequency": _AUTO_FREQUENCY,
}


def _clean_frequency(raw):
    if not isinstance(raw, dict) or raw.get("manual") is not True:
        return dict(_AUTO_FREQUENCY)
    minimum = raw.get("min_khz")
    maximum = raw.get("max_khz")
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or minimum <= 0
        or minimum > maximum
    ):
        return dict(_AUTO_FREQUENCY)
    return {"manual": True, "min_khz": minimum, "max_khz": maximum}


class CpuProfileStore(ScopedProfileStore):
    """Per-game CPU controls (SMT / boost / active cores): global + per-appid overrides
    with a per-game follow_global toggle. See ScopedProfileStore for the scope contract."""

    def _clean_global(self, raw):
        base = {**_DEFAULTS, "frequency": dict(_AUTO_FREQUENCY)}
        if isinstance(raw, dict):
            if isinstance(raw.get("smt"), bool):
                base["smt"] = raw["smt"]
            if isinstance(raw.get("boost"), bool):
                base["boost"] = raw["boost"]
            base["cores"] = int(raw["cores"]) if isinstance(raw.get("cores"), int) else None
            base["frequency"] = _clean_frequency(raw.get("frequency"))
        return base

    def effective(self, appid):
        e = self._effective_prof(appid)
        return {"smt": bool(e.get("smt", True)),
                "boost": bool(e.get("boost", True)),
                "cores": e.get("cores"),
                "frequency": _clean_frequency(e.get("frequency"))}

    def set_smt(self, scope, enabled, appid=None):
        self._target(scope, appid)["smt"] = bool(enabled)
        self._save()

    def set_boost(self, scope, enabled, appid=None):
        self._target(scope, appid)["boost"] = bool(enabled)
        self._save()

    def set_cores(self, scope, count, appid=None):
        self._target(scope, appid)["cores"] = int(count)
        self._save()

    def set_frequency(self, scope, minimum_khz, maximum_khz, appid=None):
        frequency = _clean_frequency({
            "manual": True,
            "min_khz": minimum_khz,
            "max_khz": maximum_khz,
        })
        if not frequency["manual"]:
            raise ValueError("invalid CPU frequency window")
        self._target(scope, appid)["frequency"] = frequency
        self._save()

    def set_frequency_auto(self, scope, appid=None):
        self._target(scope, appid)["frequency"] = dict(_AUTO_FREQUENCY)
        self._save()
