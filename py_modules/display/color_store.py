from scoped_store import ScopedProfileStore
from display.const import NATIVE as _NATIVE
from display.const import CALIBRATION as _CALIBRATION

# Contrast is floored at -60 and each gain at 50 so a mis-drag can never crush the panel
# to an unreadable grey/black. Every field in NATIVE must have a range here.
_RANGES = {
    "saturation": (0, 200),
    "temperature": (-100, 100),
    "contrast": (-60, 60),
    "gamma": (-100, 100),
    "hue": (-100, 100),
    "black": (-100, 100),
    "gain_r": (50, 150),
    "gain_g": (50, 150),
    "gain_b": (50, 150),
    "vibrance": (-100, 100),
}

# A missing range would KeyError out of the synchronous _init (hanging the panel);
# fail loudly at import instead.
_missing = set(_NATIVE) - set(_RANGES)
if _missing:
    raise RuntimeError(f"color fields without a range: {sorted(_missing)}")


def _clamp(field, value):
    lo, hi = _RANGES[field]
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return _NATIVE[field]


def sanitize_calibration(fields):
    """Clamp a calibration patch to the safe ranges — the one definition of "safe",
    used by both the live preview and the saved value. Returns only known calibration
    fields, as clamped ints."""
    if not isinstance(fields, dict):
        return {}
    return {f: _clamp(f, fields[f]) for f in _CALIBRATION if f in fields}


class ColorStore(ScopedProfileStore):
    """Panel color settings. The WHOLE profile (saturation + calibration:
    temperature/contrast/gamma/hue/gains/vibrance + HDR mode) is per-game. See
    ScopedProfileStore for the scope contract."""

    def _clean_global(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        prof = {f: _clamp(f, raw.get(f, _NATIVE[f])) for f in _NATIVE}
        if raw.get("hdr"):
            prof["hdr"] = True  # HDR on/off is part of the per-scope display profile
        return prof

    def _clean_game(self, raw, glob):
        # Older stores kept ONLY saturation per game (calibration was global). Preserve
        # that intent: keep the global calibration, override just the saturation, so the
        # game doesn't drop to native calibration on load.
        if (isinstance(raw, dict) and "saturation" in raw
                and not raw.get("follow_global")
                and not any(f in raw for f in _CALIBRATION)):
            prof = {k: v for k, v in glob.items() if k != "follow_global"}
            prof["saturation"] = _clamp("saturation", raw["saturation"])
            return prof
        prof = self._clean_global(raw)
        if isinstance(raw, dict) and raw.get("follow_global"):
            prof["follow_global"] = True
        return prof

    def effective(self, appid):
        e = self._effective_prof(appid)
        return {f: e[f] for f in _NATIVE}

    def hdr(self, appid):
        return bool(self._effective_prof(appid).get("hdr", False))

    def set_hdr(self, scope, enabled, appid=None):
        self._target(scope, appid)["hdr"] = bool(enabled)
        self._save()

    def set_saturation(self, scope, value, appid=None):
        self._target(scope, appid)["saturation"] = _clamp("saturation", value)
        self._save()

    def set_calibration(self, scope, appid=None, **fields):
        t = self._target(scope, appid)
        for f in _CALIBRATION:
            if f in fields:
                t[f] = _clamp(f, fields[f])
        self._save()

    def apply_preset(self, scope, preset, appid=None):
        """Overwrite a scope's profile from a preset dict (per-model OLED look): the full
        calibration + saturation in one write. Missing fields → native. HDR is a display
        mode, not part of a look, so the scope's current HDR is kept across the change."""
        prof = self._clean_global(preset)
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            if self.hdr(appid):
                prof["hdr"] = True  # keep the game's effective HDR
            self._data["games"][str(appid)] = prof  # replaces → own active (no follow_global)
        else:
            if self._data["global"].get("hdr"):
                prof["hdr"] = True
            self._data["global"] = prof
        self._save()

    def reset(self):
        """Back to the panel's native look: native global + no game overrides. HDR is a
        display mode, not a look, so it survives a color reset (kept from global)."""
        glob = dict(_NATIVE)
        if self._data["global"].get("hdr"):
            glob["hdr"] = True
        self._data = {"global": glob, "games": {}}
        self._save()
