from scoped_store import ScopedProfileStore

from audio.const import ROUTES, clamp_gain, compute_preamp


def _clean_setting(raw):
    raw = raw if isinstance(raw, dict) else {}
    gains = raw.get("gains")
    if not isinstance(gains, list) or len(gains) != 10:
        gains = [0.0] * 10
    gains = [clamp_gain(g) for g in gains]
    preset = raw.get("preset")
    preset = preset if isinstance(preset, str) else "flat"
    try:
        preamp = float(raw["preamp"])
    except (KeyError, TypeError, ValueError):
        preamp = compute_preamp(gains)
    return {"preset": preset, "gains": gains, "preamp": preamp}


class EqStore(ScopedProfileStore):
    """Per-game audio EQ. Each scope's profile holds one EQ setting per output route
    (speaker / headphone): ``{route: {preset, gains[10], preamp}}``. Scope contract
    (global + per-game follow-global) is inherited; the route lives inside the profile.
    Setters always REPLACE a route's setting with a fresh dict so a game seeded from
    global (shallow copy) never mutates global's nested settings."""

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        return {r: _clean_setting(raw.get(r)) for r in ROUTES}

    def effective(self, appid, route):
        prof = self._effective_prof(appid)
        s = _clean_setting(prof.get(route))
        return {"preset": s["preset"], "gains": list(s["gains"]), "preamp": s["preamp"]}

    def set_setting(self, scope, route, setting, appid=None):
        if route not in ROUTES:
            return
        self._target(scope, appid)[route] = _clean_setting(setting)
        self._save()

    def set_band(self, scope, route, index, gain, appid=None):
        if route not in ROUTES or not (0 <= index < 10):
            return
        prof = self._target(scope, appid)
        gains = list(_clean_setting(prof.get(route))["gains"])
        gains[index] = clamp_gain(gain)
        prof[route] = {"preset": "custom", "gains": gains, "preamp": compute_preamp(gains)}
        self._save()

    def set_bands(self, scope, route, gains, appid=None):
        """Replace all 10 band gains for a route (drag-commit of the whole curve): clamp,
        pad/truncate to 10, mark custom, recompute the anti-clip preamp. The canonical
        setting shape lives here, not in the caller."""
        if route not in ROUTES:
            return
        clean = [clamp_gain(g) for g in (gains or [])][:10]
        clean += [0.0] * (10 - len(clean))
        self._target(scope, appid)[route] = {
            "preset": "custom", "gains": clean, "preamp": compute_preamp(clean),
        }
        self._save()

    def reset(self, scope, route, appid=None):
        if route not in ROUTES:
            return
        self._target(scope, appid)[route] = _clean_setting(None)
        self._save()
