import copy

from scoped_store import ScopedProfileStore

_CHANNELS = ("system", "gpu")
_PRESETS = ("auto", "silent", "balanced", "performance", "custom")


def _clean_channel(raw):
    if not isinstance(raw, dict) or raw.get("preset") not in _PRESETS:
        return {"preset": "auto", "points": None}
    preset = raw["preset"]
    if preset == "auto":
        return {"preset": "auto", "points": None}
    points = raw.get("points")
    try:
        clean = [[int(temp), int(pwm)] for temp, pwm in points]
    except (TypeError, ValueError):
        return {"preset": "auto", "points": None}
    if not clean:
        return {"preset": "auto", "points": None}
    return {"preset": preset, "points": clean}


class DesktopFanStore(ScopedProfileStore):
    def _auto(self):
        return {key: {"preset": "auto", "points": None} for key in _CHANNELS}

    def _clean_global(self, raw):
        if not isinstance(raw, dict):
            return self._auto()
        return {key: _clean_channel(raw.get(key)) for key in _CHANNELS}

    def _new_game_from_global(self):
        return copy.deepcopy(self._data["global"])

    def effective(self, appid):
        return copy.deepcopy(self._effective_prof(appid))

    def checkpoint(self):
        return copy.deepcopy(self._data)

    def restore_checkpoint(self, checkpoint):
        self._data = copy.deepcopy(checkpoint)
        self._save()

    def set_channel(self, scope, channel, preset, points=None, appid=None):
        if channel not in _CHANNELS or preset not in _PRESETS:
            return False
        target = self._target(scope, appid)
        if preset == "auto":
            target[channel] = {"preset": "auto", "points": None}
        else:
            clean = _clean_channel({"preset": preset, "points": points})
            if clean["preset"] == "auto":
                return False
            target[channel] = clean
        self._save()
        return True
