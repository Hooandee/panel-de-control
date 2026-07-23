from scoped_store import ScopedProfileStore

from audio.const import ROUTES, WIDTH_NEUTRAL, clamp_gain, clamp_pct, compute_preamp


def _clean_bass(value):
    return clamp_pct(value)


def _clean_width(value):
    """Stereo width dial (0-100); absent/invalid means neutral (50), not silence."""
    return clamp_pct(value, WIDTH_NEUTRAL)


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
        "crossfeed": clamp_pct(raw.get("crossfeed")),
        "stereo_width": _clean_width(raw.get("stereo_width")),
    }


class EqStore(ScopedProfileStore):
    """Per-game audio EQ. Each scope's profile holds one setting per output route
    (speaker / headphone):
    ``{route: {preset, gains[10], preamp, bass, loudness, crossfeed, stereo_width}}``. Bass,
    loudness (compression) and the spatial effects (crossfeed on headphones, stereo width on
    speakers) are orthogonal to the EQ curve, so every setter PRESERVES the fields it doesn't
    touch. Setters always write a fresh route dict so a game seeded from global (shallow copy)
    never mutates global's nested settings."""

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        return {r: _clean_setting(raw.get(r)) for r in ROUTES}

    def effective(self, appid, route):
        s = _clean_setting(self._effective_prof(appid).get(route))
        # Spatial effects are route-exclusive: crossfeed only affects headphones, stereo
        # width only affects speakers. Project the route's applicable values (neutral on the
        # other route) so every caller gets a graph-ready setting without re-deriving the rule.
        # The stored values are untouched — switching routes reveals each side's own setting.
        return {
            "preset": s["preset"], "gains": list(s["gains"]), "preamp": s["preamp"],
            "bass": s["bass"], "loudness": s["loudness"],
            "crossfeed": s["crossfeed"] if route == "headphone" else 0,
            "stereo_width": s["stereo_width"] if route == "speaker" else WIDTH_NEUTRAL,
        }

    def _cur(self, scope, appid, route):
        """The route's current setting (cleaned) within the scope's mutable profile."""
        return _clean_setting(self._target(scope, appid).get(route))

    def set_setting(self, scope, route, setting, appid=None):
        """Apply an EQ curve (preset/gains) to a route, PRESERVING its bass, loudness and
        spatial effects (crossfeed / stereo width)."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        new = _clean_setting(setting)
        cur["preset"], cur["gains"], cur["preamp"] = new["preset"], new["gains"], new["preamp"]
        self._target(scope, appid)[route] = cur
        self._save()

    def set_band(self, scope, route, index, gain, appid=None):
        if route not in ROUTES or not (0 <= index < 10):
            return
        cur = self._cur(scope, appid, route)
        gains = list(cur["gains"])
        gains[index] = clamp_gain(gain)
        cur["preset"], cur["gains"], cur["preamp"] = "custom", gains, compute_preamp(gains)
        self._target(scope, appid)[route] = cur
        self._save()

    def set_bands(self, scope, route, gains, appid=None):
        """Replace all 10 band gains for a route (drag-commit of the whole curve),
        preserving the non-EQ fields. Clamp, pad/truncate to 10, mark custom, recompute preamp."""
        if route not in ROUTES:
            return
        clean = [clamp_gain(g) for g in (gains or [])][:10]
        clean += [0.0] * (10 - len(clean))
        cur = self._cur(scope, appid, route)
        cur["preset"], cur["gains"], cur["preamp"] = "custom", clean, compute_preamp(clean)
        self._target(scope, appid)[route] = cur
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

    def set_crossfeed(self, scope, route, value, appid=None):
        """Set headphone crossfeed intensity (0-100) for a route, preserving the EQ curve."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        cur["crossfeed"] = clamp_pct(value)
        self._target(scope, appid)[route] = cur
        self._save()

    def set_stereo_width(self, scope, route, value, appid=None):
        """Set speaker stereo width (0-100, 50 neutral) for a route, preserving the EQ curve."""
        if route not in ROUTES:
            return
        cur = self._cur(scope, appid, route)
        cur["stereo_width"] = _clean_width(value)
        self._target(scope, appid)[route] = cur
        self._save()

    def reset(self, scope, route, appid=None):
        """Neutral route: flat curve + no bass enhancement + no compression."""
        if route not in ROUTES:
            return
        self._target(scope, appid)[route] = _clean_setting(None)
        self._save()
