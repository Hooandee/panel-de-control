from scoped_store import ScopedProfileStore

from audio.const import ROUTES, clamp_gain, compute_preamp


def _clean_bass(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


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
    return {
        "preset": preset, "gains": gains, "preamp": preamp,
        "bass": _clean_bass(raw.get("bass")), "loudness": bool(raw.get("loudness")),
    }


class EqStore(ScopedProfileStore):
    """Per-game audio EQ. Each scope's profile holds one setting per output route
    (speaker / headphone): ``{route: {preset, gains[10], preamp, bass, loudness}}``. Bass
    enhancement and loudness (compression) are orthogonal to the EQ curve, so every setter
    PRESERVES the fields it doesn't touch. Setters always write a fresh route dict so a game
    seeded from global (shallow copy) never mutates global's nested settings."""

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        return {r: _clean_setting(raw.get(r)) for r in ROUTES}

    def effective(self, appid, route):
        s = _clean_setting(self._effective_prof(appid).get(route))
        return {
            "preset": s["preset"], "gains": list(s["gains"]), "preamp": s["preamp"],
            "bass": s["bass"], "loudness": s["loudness"],
        }

    def _cur(self, scope, appid, route):
        """The route's current setting (cleaned) within the scope's mutable profile."""
        return _clean_setting(self._target(scope, appid).get(route))

    def set_setting(self, scope, route, setting, appid=None):
        """Apply an EQ curve (preset/gains) to a route, PRESERVING its bass + loudness."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        new = _clean_setting(setting)
        new["bass"], new["loudness"] = cur["bass"], cur["loudness"]
        self._target(scope, appid)[route] = new
        self._save()

    def set_band(self, scope, route, index, gain, appid=None):
        if route not in ROUTES or not (0 <= index < 10):
            return
        cur = self._cur(scope, appid, route)
        gains = list(cur["gains"])
        gains[index] = clamp_gain(gain)
        self._target(scope, appid)[route] = {
            "preset": "custom", "gains": gains, "preamp": compute_preamp(gains),
            "bass": cur["bass"], "loudness": cur["loudness"],
        }
        self._save()

    def set_bands(self, scope, route, gains, appid=None):
        """Replace all 10 band gains for a route (drag-commit of the whole curve),
        preserving bass + loudness. Clamp, pad/truncate to 10, mark custom, recompute preamp."""
        if route not in ROUTES:
            return
        clean = [clamp_gain(g) for g in (gains or [])][:10]
        clean += [0.0] * (10 - len(clean))
        cur = self._cur(scope, appid, route)
        self._target(scope, appid)[route] = {
            "preset": "custom", "gains": clean, "preamp": compute_preamp(clean),
            "bass": cur["bass"], "loudness": cur["loudness"],
        }
        self._save()

    def set_bass(self, scope, route, value, appid=None):
        """Set the bass-enhancement amount (0-100) for a route, preserving the EQ curve."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        cur["bass"] = _clean_bass(value)
        self._target(scope, appid)[route] = cur
        self._save()

    def set_loudness(self, scope, route, on, appid=None):
        """Toggle volume leveling (compression) for a route, preserving the EQ curve."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        cur["loudness"] = bool(on)
        self._target(scope, appid)[route] = cur
        self._save()

    def reset(self, scope, route, appid=None):
        """Neutral route: flat curve + no bass enhancement + no compression."""
        if route not in ROUTES:
            return
        self._target(scope, appid)[route] = _clean_setting(None)
        self._save()
