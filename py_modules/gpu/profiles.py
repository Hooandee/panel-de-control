from scoped_store import ScopedProfileStore


def _clean_clock(raw):
    if not isinstance(raw, dict) or not raw.get("manual"):
        return {"manual": False, "min": None, "max": None}
    try:
        minimum = int(raw.get("min"))
        maximum = int(raw.get("max"))
    except (TypeError, ValueError, OverflowError):
        return {"manual": False, "min": None, "max": None}
    if minimum <= 0 or maximum < minimum:
        return {"manual": False, "min": None, "max": None}
    return {"manual": True, "min": minimum, "max": maximum}


class GpuProfileStore(ScopedProfileStore):
    def _clean_global(self, raw):
        return _clean_clock(raw)

    def clock(self, appid):
        return dict(self._effective_prof(appid))

    def set_clock(self, scope, manual, minimum, maximum, appid=None):
        profile = (
            _clean_clock({"manual": True, "min": minimum, "max": maximum})
            if manual
            else {"manual": False, "min": None, "max": None}
        )
        self._set_profile(scope, appid, profile)
