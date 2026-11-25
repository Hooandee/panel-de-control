import json
import math
from threading import RLock

from json_store import atomic_json_save


class OwnershipConflict(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _appid(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("invalid_appid")
    value = str(value)
    if not value.strip():
        raise ValueError("invalid_appid")
    return value


_STEAM_TOGGLES = frozenset({"disableFrameLimit", "variableResolution", "vrr", "allowTearing"})
_STEAM_NUMBERS = frozenset({"legacyFrameRate", "appFrameRate", "refreshRate", "splitScalingFilter", "scalingMode", "sharpness", "combinedScaling", "fsrSharpness", "nisSharpness"})


def validate_steam_settings(value):
    if not isinstance(value, dict) or len(value) > 20:
        raise ValueError("invalid_steam_settings")
    for key, setting in value.items():
        if key in _STEAM_TOGGLES:
            valid = type(setting) is bool
        elif key in _STEAM_NUMBERS:
            valid = type(setting) in (int, float) and setting >= 0
            if valid and isinstance(setting, float):
                valid = math.isfinite(setting)
        else:
            valid = False
        if not valid:
            raise ValueError("invalid_steam_settings")
    return dict(value)


class PowerOwnershipStore:
    """Persistent game choices, with transient frontend observations.

    Without saved choices, an absent observation preserves legacy consumers.
    Saved choices require a known context before global power can be applied.
    """

    def __init__(self, path):
        self._path = path
        self._lock = RLock()
        self._owners, self._steam_settings = self._load()
        self._context_appid = None
        self._steam_profile = None
        self._revision = 0

    def _load(self):
        try:
            with open(self._path) as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}, {}
        games = raw.get("games") if isinstance(raw, dict) else None
        if not isinstance(games, dict):
            return {}, {}
        owners, settings = {}, {}
        for appid, entry in games.items():
            if not appid.strip() or not isinstance(entry, dict) or entry.get("owner") not in ("steam", "pdc"):
                continue
            owners[appid] = entry["owner"]
            try:
                settings[appid] = validate_steam_settings(entry.get("steam_settings", {}))
            except ValueError:
                settings[appid] = {}
        return owners, settings

    def _persist(self, owners, settings):
        atomic_json_save(self._path, {
            "version": 1,
            "games": {
                key: {"owner": value, "steam_settings": settings.get(key, {})}
                for key, value in owners.items()
            },
        })
        self._owners = owners
        self._steam_settings = settings
        self._revision += 1

    def _check_context(self, appid, expected_revision):
        if appid != self._context_appid:
            raise OwnershipConflict("stale_context")
        if type(expected_revision) is not int or expected_revision != self._revision:
            raise OwnershipConflict("stale_revision")

    def state(self):
        with self._lock:
            explicit = self._owners.get(self._context_appid)
            if explicit is not None:
                owner, reason = explicit, "explicit_choice"
            elif self._steam_profile is None and self._owners:
                owner, reason = "unresolved", "awaiting_context"
            elif self._steam_profile is None:
                owner, reason = "pdc", "unobserved_legacy"
            elif self._steam_profile == "active":
                owner, reason = "steam", "steam_profile_active"
            elif self._steam_profile == "inactive":
                owner, reason = "pdc", "steam_profile_inactive"
            else:
                owner, reason = "unresolved", "steam_profile_unknown"
            return {
                "context_appid": self._context_appid,
                "revision": self._revision,
                "observed": self._steam_profile is not None,
                "steam_profile": self._steam_profile,
                "explicit_owner": explicit,
                "owner": owner,
                "write_allowed": owner == "pdc",
                "reason": reason,
                "steam_settings": dict(self._steam_settings.get(self._context_appid, {})),
            }

    def set_context(self, appid):
        appid = _appid(appid)
        with self._lock:
            if appid != self._context_appid:
                self._context_appid = appid
                self._steam_profile = None
                self._revision += 1
            return self.state()

    def observe(self, appid, steam_profile):
        appid = _appid(appid)
        if steam_profile not in ("active", "inactive", "unknown"):
            raise ValueError("invalid_steam_profile")
        with self._lock:
            if (appid, steam_profile) != (self._context_appid, self._steam_profile):
                self._context_appid = appid
                self._steam_profile = steam_profile
                self._revision += 1
            return self.state()

    def set_owner(self, appid, owner, expected_revision, steam_settings=None):
        appid = _appid(appid)
        if appid is None:
            raise ValueError("game_required")
        if owner not in ("steam", "pdc"):
            raise ValueError("invalid_owner")
        snapshot = validate_steam_settings(steam_settings) if steam_settings is not None else None
        with self._lock:
            self._check_context(appid, expected_revision)
            settings = self._steam_settings
            if snapshot is not None:
                settings = {**settings, appid: snapshot}
            if self._owners.get(appid) != owner or settings != self._steam_settings:
                self._persist({**self._owners, appid: owner}, settings)
            return self.state()

    def set_steam_setting(self, appid, expected_revision, id, value):
        appid = _appid(appid)
        if appid is None:
            raise ValueError("game_required")
        if not isinstance(id, str):
            raise ValueError("invalid_steam_settings")
        update = validate_steam_settings({id: value})
        with self._lock:
            self._check_context(appid, expected_revision)
            if self._owners.get(appid) != "pdc":
                raise OwnershipConflict("pdc_owner_required")
            snapshot = validate_steam_settings({**self._steam_settings.get(appid, {}), **update})
            self._persist(self._owners, {**self._steam_settings, appid: snapshot})
            return self.state()
