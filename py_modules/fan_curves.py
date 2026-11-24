import copy

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


def _clean_points(raw):
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return [[int(t), int(p)] for t, p in raw]
    except (TypeError, ValueError, OverflowError):
        return None


# Per-channel ("por separado") curves: ASUS exposes two hardware tables, pwm1 = CPU and
# pwm2 = GPU. The joined curve (`preset`/`points`/`custom_points`) is never touched while a
# profile is split, so switching back restores it as it was.
CHANNELS = ("cpu", "gpu")
_SPLIT_KEYS = ("split", "split_preset", "points_by_channel", "custom_points_by_channel")
_SPLIT_PRESETS = {"auto", "silent", "balanced", "performance", "custom"}


def _clean_by_channel(raw):
    if not isinstance(raw, dict):
        return None
    cleaned = {channel: _clean_points(raw.get(channel)) for channel in CHANNELS}
    return cleaned if all(cleaned.values()) else None


class FanCurveStore(ScopedProfileStore):
    """Global fan-curve profile + per-appid overrides. See ScopedProfileStore for the
    scope contract.

    Profile = {"preset": str, "points": list|None}. preset in {"auto","adaptive"}
    => points None. `adaptive` additionally carries a `bias` (silence↔cool
    preference, -100..100). Otherwise points is an 8-element [[temp,pwm],...] list.
    Outside custom, optional `custom_points` remembers the last manual curve.
    Default = auto.

    A profile may additionally be `split` (key absent = joined): `split_preset` and
    `points_by_channel` {cpu, gpu} then drive each fan on its own, while
    `preset`/`points` keep the joined curve untouched. `custom_points_by_channel`
    remembers the last manual per-channel pair outside custom.
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
            profile = self._adaptive(raw.get("bias", 0))
        elif preset not in _VALID or preset == "auto":
            profile = self._auto()
        else:
            points = _clean_points(raw.get("points"))
            profile = {"preset": preset, "points": points} if points else self._auto()
        if preset != "custom":
            custom_points = _clean_points(raw.get("custom_points"))
            if custom_points:
                profile["custom_points"] = custom_points
        split_preset = None
        if raw.get("split") is True:
            split_preset = raw.get("split_preset")
            by_channel = _clean_by_channel(raw.get("points_by_channel"))
            if split_preset not in _SPLIT_PRESETS or (split_preset != "auto" and not by_channel):
                split_preset, by_channel = "auto", None
            profile["split"] = True
            profile["split_preset"] = split_preset
            if split_preset != "auto":
                profile["points_by_channel"] = by_channel
        if split_preset != "custom":
            remembered = _clean_by_channel(raw.get("custom_points_by_channel"))
            if remembered:
                profile["custom_points_by_channel"] = remembered
        return profile

    def _new_game_from_global(self):
        return copy.deepcopy(super()._new_game_from_global())

    def effective(self, appid):
        return dict(self._effective_prof(appid))

    def is_split(self, appid):
        return bool(self._effective_prof(appid).get("split"))

    def is_adaptive(self, appid):
        """Whether the effective (own or inherited-global) curve is the adaptive mode.

        The drive path and the periodic re-fit gate on this: the learner runs ONLY
        when the user has explicitly selected Adaptive for the effective scope."""
        prof = self._effective_prof(appid)
        return prof.get("preset") == "adaptive" and not prof.get("split")

    def adaptive_bias(self, appid):
        """The silence↔cool bias (-100..100) of the effective adaptive profile (0 otherwise)."""
        return _clamp_bias(self._effective_prof(appid).get("bias", 0))

    def _set_mode(self, scope, profile, appid=None):
        previous = self._target(scope, appid)
        remembered = previous.get("points") if previous.get("preset") == "custom" else previous.get("custom_points")
        custom_points = _clean_points(remembered)
        if profile["preset"] != "custom" and custom_points:
            profile["custom_points"] = custom_points
        self._carry_split(previous, profile)
        self._set_profile(scope, appid, profile)

    @staticmethod
    def _carry_split(previous, profile):
        """Joined setters rebuild the profile; the per-channel state must survive them."""
        for key in _SPLIT_KEYS:
            if key in previous:
                profile[key] = copy.deepcopy(previous[key])

    def set_preset(self, scope, preset_id, points, appid=None):
        self._set_mode(scope, {"preset": preset_id, "points": [list(p) for p in points]}, appid)

    def set_custom(self, scope, points, appid=None):
        previous = self._target(scope, appid)
        profile = {"preset": "custom", "points": [list(p) for p in points]}
        self._carry_split(previous, profile)
        self._set_profile(scope, appid, profile)

    def set_adaptive(self, scope, appid=None):
        """Select the adaptive (learned) mode for a scope (bias reset to neutral)."""
        self._set_mode(scope, self._adaptive(), appid)

    def set_adaptive_bias(self, scope, bias, appid=None):
        """Select adaptive and set its silence↔cool bias (-100..100)."""
        self._set_mode(scope, self._adaptive(bias), appid)

    def set_auto(self, scope, appid=None):
        self._set_mode(scope, self._auto(), appid)

    # --- per-channel ("por separado") -----------------------------------------

    def split_state(self, appid):
        """(split_preset, {cpu: pts, gpu: pts}|None) of the effective profile, or None when joined."""
        prof = self._effective_prof(appid)
        if not prof.get("split"):
            return None
        by_channel = prof.get("points_by_channel")
        return prof.get("split_preset", "auto"), copy.deepcopy(by_channel) if by_channel else None

    def is_split_scope(self, scope, appid=None):
        """Whether the profile a write to *scope* would land on is split (a game with no own
        profile inherits global's, which is what `_target` seeds it from)."""
        if scope == "game" and appid is not None and str(appid) in self._data["games"]:
            return bool(self._data["games"][str(appid)].get("split"))
        return bool(self._data["global"].get("split"))

    def set_split(self, scope, split, seed_points=None, appid=None):
        """Turn per-channel mode on/off. On: both channels are seeded with the current curve
        (`seed_points`, else the profile's own points). Off: the joined curve is untouched."""
        target = self._target(scope, appid)
        if bool(split) == bool(target.get("split")):
            return
        if split:
            seed = _clean_points(seed_points) or _clean_points(target.get("points"))
            target["split"] = True
            remembered = target.get("custom_points_by_channel") or {}
            if all(_clean_points(remembered.get(channel)) for channel in CHANNELS):
                target["split_preset"] = "custom"
                target["points_by_channel"] = copy.deepcopy(remembered)
            elif seed:
                same_curve = target.get("points") == seed and target.get("preset") in _SPLIT_PRESETS
                target["split_preset"] = target["preset"] if same_curve else "custom"
                target["points_by_channel"] = {channel: [list(p) for p in seed] for channel in CHANNELS}
                if target["split_preset"] == "custom":
                    target.pop("custom_points_by_channel", None)
            else:
                target["split_preset"] = "auto"
                target.pop("points_by_channel", None)
        else:
            self._remember_channels(target)
            for key in ("split", "split_preset", "points_by_channel"):
                target.pop(key, None)
        self._save()

    @staticmethod
    def _remember_channels(target):
        if target.get("split_preset") == "custom" and target.get("points_by_channel"):
            target["custom_points_by_channel"] = copy.deepcopy(target["points_by_channel"])

    def set_split_preset(self, scope, preset_id, points, appid=None):
        """A preset applies to BOTH channels; each can then be edited by hand."""
        target = self._target(scope, appid)
        if not target.get("split"):
            return
        self._remember_channels(target)
        target["split_preset"] = preset_id
        target["points_by_channel"] = {channel: [list(p) for p in points] for channel in CHANNELS}
        self._save()

    def set_split_auto(self, scope, appid=None):
        target = self._target(scope, appid)
        if not target.get("split"):
            return
        self._remember_channels(target)
        target["split_preset"] = "auto"
        target.pop("points_by_channel", None)
        self._save()

    def set_split_custom(self, scope, channel, points, appid=None):
        """Hand-edit ONE channel; the other keeps its current curve (or the remembered
        manual pair, else the joined curve)."""
        if channel not in CHANNELS:
            return
        target = self._target(scope, appid)
        if not target.get("split"):
            return
        if target.get("split_preset") != "custom" or not target.get("points_by_channel"):
            base = (target.get("points_by_channel") or target.get("custom_points_by_channel")
                    or {c: target.get("points") for c in CHANNELS})
            self._remember_channels(target)
            target["points_by_channel"] = {
                c: [list(p) for p in (base.get(c) or points)] for c in CHANNELS}
        target["split_preset"] = "custom"
        target["points_by_channel"][channel] = [list(p) for p in points]
        self._save()

    def set_split_custom_both(self, scope, points, appid=None):
        for channel in CHANNELS:
            self.set_split_custom(scope, channel, points, appid)
