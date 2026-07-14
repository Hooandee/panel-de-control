from scoped_store import ScopedProfileStore

# Curve modes. `auto` = firmware control (no points). `adaptive` = the learned
# curve, computed live from telemetry when driven (no stored points; a per-scope
# silence↔cool `bias` is the only persisted preference). The rest carry 8 points.
_VALID = {"auto", "adaptive", "silent", "balanced", "performance", "custom"}
# Modes that carry NO stored points — the curve is produced elsewhere (firmware /
# the learner) rather than stored here.
_POINTLESS = {"auto", "adaptive"}


def _clamp_bias(v):
    try:
        return max(-100, min(100, int(v)))
    except (TypeError, ValueError):
        return 0


class FanCurveStore(ScopedProfileStore):
    """Global fan-curve profile + per-appid overrides. See ScopedProfileStore for the
    scope contract.

    Profile = {"preset": str, "points": list|None}. preset in {"auto","adaptive"}
    => points None. `adaptive` additionally carries a `bias` (silence↔cool
    preference, -100..100). Otherwise points is an 8-element [[temp,pwm],...] list.
    Default = auto.
    """

    def _auto(self):
        return {"preset": "auto", "points": None}

    def _adaptive(self, bias=0):
        return {"preset": "adaptive", "points": None, "bias": _clamp_bias(bias)}

    def _clean_global(self, raw):
        if not isinstance(raw, dict):
            return self._auto()
        preset = raw.get("preset")
        # Migration: a legacy auto-applied curve was stored as custom + learned:true.
        # The learned curve is now the `adaptive` MODE (recomputed live), so fold it
        # in and drop the dead flag. A hand-set custom (no `learned`) stays custom.
        if raw.get("learned") and preset == "custom":
            return self._adaptive()
        if preset == "adaptive":
            return self._adaptive(raw.get("bias", 0))
        if preset not in _VALID or preset == "auto":
            return self._auto()
        pts = raw.get("points")
        if not isinstance(pts, list) or not pts:
            return self._auto()
        try:
            points = [[int(t), int(p)] for t, p in pts]
        except (TypeError, ValueError):
            return self._auto()
        return {"preset": preset, "points": points}

    def effective(self, appid):
        return dict(self._effective_prof(appid))

    def is_adaptive(self, appid):
        """Whether the effective (own or inherited-global) curve is the adaptive mode.

        The drive path and the periodic re-fit gate on this: the learner runs ONLY
        when the user has explicitly selected Adaptive for the effective scope."""
        return self._effective_prof(appid).get("preset") == "adaptive"

    def adaptive_bias(self, appid):
        """The silence↔cool bias (-100..100) of the effective adaptive profile (0 otherwise)."""
        return _clamp_bias(self._effective_prof(appid).get("bias", 0))

    def set_preset(self, scope, preset_id, points, appid=None):
        self._set_profile(scope, appid, {"preset": preset_id, "points": [list(p) for p in points]})

    def set_custom(self, scope, points, appid=None):
        self._set_profile(scope, appid, {"preset": "custom", "points": [list(p) for p in points]})

    def set_adaptive(self, scope, appid=None):
        """Select the adaptive (learned) mode for a scope (bias reset to neutral)."""
        self._set_profile(scope, appid, self._adaptive())

    def set_adaptive_bias(self, scope, bias, appid=None):
        """Select adaptive and set its silence↔cool bias (-100..100)."""
        self._set_profile(scope, appid, self._adaptive(bias))

    def set_auto(self, scope, appid=None):
        self._set_profile(scope, appid, self._auto())
