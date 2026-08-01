"""Persisted controller-remap overrides, per scope (global + per-game).

Holds ``{global: {source: targets}, games: {appid: {overrides, follow_global}}}``.
A game applies the global overrides until it has its own profile with
follow_global=False (mirrors tdp_profiles.ProfileStore). Switching scope never
deletes either side. JSON, atomic write, robust load (never raises). Migrates the
old flat ``{source: targets}`` shape into ``global``.
"""
import json
import math

from json_store import atomic_json_save


def _clean_overrides(raw) -> dict:
    return {k: v for k, v in raw.items() if isinstance(v, list)} if isinstance(raw, dict) else {}


def _clean_vibration(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    clean = {}
    if isinstance(raw.get("enabled"), bool):
        clean["enabled"] = raw["enabled"]
    for field in ("value", "left", "right"):
        value = raw.get(field)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        ):
            clean[field] = min(100, max(0, round(float(value) / 5) * 5))
    return clean


def _clean_vibration_baselines(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        owner: clean
        for owner, value in raw.items()
        if isinstance(owner, str) and owner
        if (clean := _clean_vibration_baseline(value))
    }


def _clean_vibration_baseline(raw) -> dict:
    clean = _clean_vibration(raw)
    if not isinstance(raw, dict):
        return clean
    for field in ("native_left", "native_right"):
        value = raw.get(field)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= 255
        ):
            clean[field] = value
    return clean


def _clean_profile_states(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    states = {}
    for device_key, state in raw.items():
        if not isinstance(device_key, str) or not isinstance(state, dict):
            continue
        baseline = state.get("baseline_yaml")
        applied = state.get("last_applied_yaml")
        recovery = state.get("recovery_yamls")
        if isinstance(baseline, str) and baseline:
            clean_state = {
                "baseline_yaml": baseline,
                "last_applied_yaml": applied if isinstance(applied, str) else None,
            }
            recovery_yamls = [
                value for value in (
                    recovery if isinstance(recovery, list) else []
                )
                if isinstance(value, str) and value
            ][:4]
            if recovery_yamls:
                clean_state["recovery_yamls"] = recovery_yamls
            states[device_key] = clean_state
    return states


class RemapStore:
    def __init__(self, path: str):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        return self._coerce(raw)

    def _coerce(self, raw) -> dict:
        if not isinstance(raw, dict):
            return {
                "global": {}, "vibration": {}, "games": {},
                "profile_states": {}, "vibration_baselines": {},
            }
        # Old flat shape {source: targets} → migrate into the global scope.
        if "global" not in raw and "games" not in raw:
            return {
                "global": _clean_overrides(raw), "vibration": {}, "games": {},
                "profile_states": {}, "vibration_baselines": {},
            }
        games = {}
        for appid, g in (raw.get("games") or {}).items():
            if isinstance(g, dict):
                games[str(appid)] = {
                    "overrides": _clean_overrides(g.get("overrides")),
                    "vibration": _clean_vibration(g.get("vibration")),
                    "follow_global": bool(g.get("follow_global")),
                }
        return {
            "global": _clean_overrides(raw.get("global")),
            "vibration": _clean_vibration(raw.get("vibration")),
            "games": games,
            "profile_states": _clean_profile_states(raw.get("profile_states")),
            "vibration_baselines": _clean_vibration_baselines(
                raw.get("vibration_baselines")
            ),
        }

    def _game(self, appid):
        return self._data["games"].get(str(appid)) if appid is not None else None

    def is_following_global(self, appid) -> bool:
        g = self._game(appid)
        return g is None or bool(g.get("follow_global"))

    def set_follow_global(self, appid, follow: bool) -> None:
        g = self._game(appid)
        if g is not None:
            g["follow_global"] = bool(follow)
            self._save()

    def effective_overrides(self, appid) -> dict:
        """The overrides that actually apply for the running game (global when it
        follows global, else its own). A copy — callers must not mutate the store."""
        if self.is_following_global(appid):
            return dict(self._data["global"])
        return dict(self._game(appid)["overrides"])

    def effective_vibration(self, appid) -> dict:
        if self.is_following_global(appid):
            return dict(self._data["vibration"])
        return dict(self._game(appid)["vibration"])

    def effective_profile(self, appid) -> dict:
        return {
            "buttons": self.effective_overrides(appid),
            "vibration": self.effective_vibration(appid),
        }

    def vibration_baseline(self, owner: str) -> dict:
        return dict(self._data["vibration_baselines"].get(owner, {}))

    def remember_vibration_baseline(self, owner: str, patch: dict) -> None:
        if not isinstance(owner, str) or not owner:
            return
        baseline = self._data["vibration_baselines"].setdefault(owner, {})
        clean = _clean_vibration_baseline(patch)
        if baseline and not all(
            field in baseline for field in ("native_left", "native_right")
        ):
            clean.pop("native_left", None)
            clean.pop("native_right", None)
        missing = {
            field: value
            for field, value in clean.items()
            if field not in baseline
        }
        if missing:
            baseline.update(missing)
            self._save()

    def profile_state(self, device_key) -> dict | None:
        state = self._data["profile_states"].get(str(device_key or ""))
        return dict(state) if state is not None else None

    def remember_profile_baseline(self, device_key, baseline_yaml: str) -> None:
        self._data["profile_states"][str(device_key or "")] = {
            "baseline_yaml": baseline_yaml,
            "last_applied_yaml": None,
        }
        self._save()

    def remember_applied_profile(self, device_key, applied_yaml: str) -> None:
        state = self._data["profile_states"].get(str(device_key or ""))
        if state is not None:
            state["last_applied_yaml"] = applied_yaml
            state.pop("recovery_yamls", None)
            self._save()

    def remember_profile_recovery(self, device_key, candidates) -> None:
        state = self._data["profile_states"].get(str(device_key or ""))
        if state is None:
            return
        state["recovery_yamls"] = list(dict.fromkeys(
            value for value in candidates
            if isinstance(value, str) and value
        ))[:4]
        self._save()

    def forget_profile_state(self, device_key) -> None:
        key = str(device_key or "")
        if key in self._data["profile_states"]:
            del self._data["profile_states"][key]
            self._save()

    def overrides_for(self, scope: str, appid=None) -> dict:
        """The overrides being viewed/edited in a specific scope. A game with no own
        profile yet shows the global set (the seed it would copy)."""
        if scope == "game" and appid is not None:
            g = self._game(appid)
            return dict(g["overrides"]) if g else dict(self._data["global"])
        return dict(self._data["global"])

    def vibration_for(self, scope: str, appid=None) -> dict:
        if scope == "game" and appid is not None:
            g = self._game(appid)
            return dict(g["vibration"]) if g else dict(self._data["vibration"])
        return dict(self._data["vibration"])

    def has_game(self, appid) -> bool:
        return str(appid) in self._data["games"]

    def list_games(self) -> list:
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid) -> None:
        self._data["games"][str(appid)] = {
            "overrides": dict(self._data["global"]),
            "vibration": dict(self._data["vibration"]),
            "follow_global": False,
        }
        self._save()

    def game_profile(self, appid):
        """The game's own stored button overrides, or None if no entry."""
        g = self._game(appid)
        return dict(g["overrides"]) if g is not None else None

    def differs_from_global(self, appid) -> bool:
        """Whether the game's own overrides actually differ from global (a bare
        scope-toggle copies global → not 'configured')."""
        g = self._game(appid)
        return g is not None and (
            g["overrides"] != self._data["global"]
            or g["vibration"] != self._data["vibration"]
        )

    def game_vibration_differs(self, appid) -> bool:
        game = self._game(appid)
        return (
            game is not None
            and game["vibration"] != self._data["vibration"]
        )

    def forget_game(self, appid) -> None:
        """Delete the game's stored remap so it reverts to global. No-op when none."""
        if str(appid) in self._data["games"]:
            del self._data["games"][str(appid)]
            self._save()

    def _target(self, scope: str, appid=None) -> dict:
        """The overrides dict to mutate for a scope. Editing a game value activates
        its own profile (follow_global=False), seeded from global on first touch."""
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            g = self._data["games"].setdefault(
                str(appid), {
                    "overrides": dict(self._data["global"]),
                    "vibration": dict(self._data["vibration"]),
                    "follow_global": False,
                })
            g["follow_global"] = False
            return g["overrides"]
        raise ValueError(f"unknown scope: {scope}")

    def replace(self, scope: str, appid, data: dict) -> None:
        tgt = self._target(scope, appid)
        tgt.clear()
        tgt.update(data)
        self._save()

    def patch_vibration(self, scope: str, appid, patch: dict) -> None:
        clean = _clean_vibration(patch)
        if not clean:
            return
        if scope == "global":
            target = self._data["vibration"]
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            game = self._data["games"].setdefault(
                str(appid), {
                    "overrides": dict(self._data["global"]),
                    "vibration": dict(self._data["vibration"]),
                    "follow_global": False,
                })
            game["follow_global"] = False
            target = game["vibration"]
        else:
            raise ValueError(f"unknown scope: {scope}")
        target.update(clean)
        self._save()

    def reset(self, scope: str, appid=None) -> None:
        self._target(scope, appid).clear()
        self._save()

    def _save(self) -> None:
        atomic_json_save(self._path, self._data)
