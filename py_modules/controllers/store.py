"""Versioned, component-scoped controller profiles."""
import copy
import json
import math
import re

from controllers import ip_profile
from json_store import atomic_json_save


_VERSION = 5
_COMPONENTS = {"buttons", "vibration", "virtual_controller"}
_MODE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_VIBRATION_INTENSITIES = {"off", "low", "medium", "high"}
_VIBRATION_PATTERNS = {"fps", "racing", "standard", "spg", "rpg"}
_VIBRATION_ROUTES = {"lenovo_hd"}
_LENOVO_NATIVE_FIELDS = (
    "intensity", "left_pattern", "right_pattern",
    "touchpad_enabled", "touchpad_intensity",
)


def _clean_button_action(raw) -> list:
    return ip_profile.sanitize_button_action(raw)


def _clean_buttons(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for source, action in raw.items():
        if not isinstance(source, str) or not source:
            continue
        target = _clean_button_action(action)
        if target:
            clean[source] = target
    return clean


def _clean_vibration(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    clean = {}
    if isinstance(raw.get("enabled"), bool):
        clean["enabled"] = raw["enabled"]
    if raw.get("intensity") in _VIBRATION_INTENSITIES:
        clean["intensity"] = raw["intensity"]
    legacy_pattern = raw.get("pattern")
    for field in ("left_pattern", "right_pattern"):
        value = raw.get(field, legacy_pattern)
        if value in _VIBRATION_PATTERNS:
            clean[field] = value
    if isinstance(raw.get("touchpad_enabled"), bool):
        clean["touchpad_enabled"] = raw["touchpad_enabled"]
    if raw.get("touchpad_intensity") in _VIBRATION_INTENSITIES:
        clean["touchpad_intensity"] = raw["touchpad_intensity"]
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


def _clean_vibration_routes(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        owner: route
        for owner, route in raw.items()
        if isinstance(owner, str) and owner and route in _VIBRATION_ROUTES
    }


def _clean_vibration_route_baseline(raw) -> dict:
    clean = _clean_vibration_baseline(raw)
    if not all(field in clean for field in _LENOVO_NATIVE_FIELDS):
        return {}
    return {field: clean[field] for field in _LENOVO_NATIVE_FIELDS}


def _clean_vibration_route_baselines(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        owner: clean
        for owner, value in raw.items()
        if isinstance(owner, str) and owner
        if (clean := _clean_vibration_route_baseline(value))
    }


def _clean_vibration_baseline(raw) -> dict:
    clean = _clean_vibration(raw)
    if not isinstance(raw, dict):
        return clean
    native_left = raw.get("native_left")
    native_right = raw.get("native_right")
    if all(
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 64
        for value in (native_left, native_right)
    ):
        clean["native_left"] = native_left
        clean["native_right"] = native_right
    return clean


def _clean_virtual_controller(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    mode = raw.get("mode")
    return {"mode": mode} if isinstance(mode, str) and _MODE.fullmatch(mode) else {}


def _clean_virtual_mode_baseline(raw) -> dict:
    clean = _clean_virtual_controller(raw)
    if not clean or not isinstance(raw, dict):
        return {}
    paddles = raw.get("paddles_as")
    if isinstance(paddles, str) and _MODE.fullmatch(paddles):
        clean["paddles_as"] = paddles
    targets = ip_profile.clean_target_devices(raw.get("target_devices"))
    if targets:
        clean["target_devices"] = targets
    applied = ip_profile.clean_target_devices(
        raw.get("last_applied_target_devices")
    )
    if applied:
        clean["last_applied_target_devices"] = applied
    recovery = [
        targets
        for value in (
            raw.get("recovery_target_devices")
            if isinstance(raw.get("recovery_target_devices"), list)
            else []
        )
        if (targets := ip_profile.clean_target_devices(value))
    ][:4]
    if recovery:
        clean["recovery_target_devices"] = recovery
    return clean


def _clean_virtual_mode_baselines(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        owner: clean
        for owner, value in raw.items()
        if isinstance(owner, str) and owner
        if (clean := _clean_virtual_mode_baseline(value))
    }


def _clean_profile(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "buttons": _clean_buttons(raw.get("buttons")),
        "vibration": _clean_vibration(raw.get("vibration")),
        "virtual_controller": _clean_virtual_controller(
            raw.get("virtual_controller")
        ),
    }


def _empty_data() -> dict:
    return {
        "version": _VERSION,
        "global": _clean_profile({}),
        "games": {},
        "profile_states": {},
        "vibration_baselines": {},
        "vibration_routes": {},
        "vibration_route_baselines": {},
        "virtual_mode_baselines": {},
    }


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
            return _empty_data()
        if raw.get("version") in {3, 4, _VERSION}:
            global_profile = _clean_profile(raw.get("global"))
            games = {}
            raw_games = raw.get("games")
            for appid, game in (
                raw_games.items() if isinstance(raw_games, dict) else []
            ):
                if not isinstance(game, dict):
                    continue
                games[str(appid)] = {
                    **_clean_profile(game),
                    "follow_global": bool(game.get("follow_global")),
                }
            return {
                "version": _VERSION,
                "global": global_profile,
                "games": games,
                "profile_states": _clean_profile_states(
                    raw.get("profile_states")
                ),
                "vibration_baselines": _clean_vibration_baselines(
                    raw.get("vibration_baselines")
                ),
                "vibration_routes": _clean_vibration_routes(
                    raw.get("vibration_routes")
                ),
                "vibration_route_baselines": (
                    _clean_vibration_route_baselines(
                        raw.get("vibration_route_baselines")
                    )
                ),
                "virtual_mode_baselines": _clean_virtual_mode_baselines(
                    raw.get("virtual_mode_baselines")
                ),
            }
        # Old flat shape {source: targets} → migrate into the global scope.
        if "global" not in raw and "games" not in raw:
            return {
                "version": _VERSION,
                "global": {
                    "buttons": _clean_buttons(raw),
                    "vibration": {},
                    "virtual_controller": {},
                },
                "games": {},
                "profile_states": {}, "vibration_baselines": {},
                "vibration_routes": {},
                "vibration_route_baselines": {},
                "virtual_mode_baselines": {},
            }
        games = {}
        raw_games = raw.get("games")
        for appid, g in (
            raw_games.items() if isinstance(raw_games, dict) else []
        ):
            if isinstance(g, dict):
                games[str(appid)] = {
                    "buttons": _clean_buttons(g.get("overrides")),
                    "vibration": _clean_vibration(g.get("vibration")),
                    "virtual_controller": {},
                    "follow_global": bool(g.get("follow_global")),
                }
        return {
            "version": _VERSION,
            "global": {
                "buttons": _clean_buttons(raw.get("global")),
                "vibration": _clean_vibration(raw.get("vibration")),
                "virtual_controller": {},
            },
            "games": games,
            "profile_states": _clean_profile_states(raw.get("profile_states")),
            "vibration_baselines": _clean_vibration_baselines(
                raw.get("vibration_baselines")
            ),
            "vibration_routes": _clean_vibration_routes(
                raw.get("vibration_routes")
            ),
            "vibration_route_baselines": _clean_vibration_route_baselines(
                raw.get("vibration_route_baselines")
            ),
            "virtual_mode_baselines": _clean_virtual_mode_baselines(
                raw.get("virtual_mode_baselines")
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
            return copy.deepcopy(self._data["global"]["buttons"])
        return copy.deepcopy(self._game(appid)["buttons"])

    def effective_vibration(self, appid) -> dict:
        if self.is_following_global(appid):
            return dict(self._data["global"]["vibration"])
        return {
            **self._data["global"]["vibration"],
            **self._game(appid)["vibration"],
        }

    def effective_virtual_controller(self, appid) -> dict:
        if self.is_following_global(appid):
            return dict(self._data["global"]["virtual_controller"])
        return dict(self._game(appid)["virtual_controller"])

    def effective_profile(self, appid) -> dict:
        return {
            "buttons": self.effective_overrides(appid),
            "vibration": self.effective_vibration(appid),
            "virtual_controller": self.effective_virtual_controller(appid),
        }

    def vibration_baseline(self, owner: str) -> dict:
        return dict(self._data["vibration_baselines"].get(owner, {}))

    def vibration_route(self, owner: str) -> str | None:
        return self._data["vibration_routes"].get(owner)

    def vibration_route_baseline(self, owner: str) -> dict:
        return dict(
            self._data["vibration_route_baselines"].get(owner, {})
        )

    def remember_vibration_route(
        self, owner: str, route: str, baseline=None
    ) -> None:
        if (
            not isinstance(owner, str)
            or not owner
            or route not in _VIBRATION_ROUTES
        ):
            return
        changed = False
        if self._data["vibration_routes"].get(owner) != route:
            self._data["vibration_routes"][owner] = route
            changed = True
        clean = _clean_vibration_route_baseline(baseline)
        if clean and owner not in self._data["vibration_route_baselines"]:
            self._data["vibration_route_baselines"][owner] = clean
            changed = True
        if changed:
            self._save()

    def remember_vibration_baseline(self, owner: str, patch: dict) -> None:
        if not isinstance(owner, str) or not owner:
            return
        baseline = self._data["vibration_baselines"].setdefault(owner, {})
        clean = _clean_vibration_baseline(patch)
        exact_groups = (
            ("native_left", "native_right"),
            (
                "intensity", "left_pattern", "right_pattern",
                "touchpad_enabled", "touchpad_intensity",
            ),
        )
        if baseline:
            for group in exact_groups:
                if not all(field in baseline for field in group):
                    for field in group:
                        clean.pop(field, None)
        missing = {
            field: value
            for field, value in clean.items()
            if field not in baseline
        }
        if missing:
            baseline.update(missing)
            self._save()

    def virtual_mode_baseline(self, owner: str) -> dict:
        return copy.deepcopy(
            self._data["virtual_mode_baselines"].get(owner, {})
        )

    def remember_virtual_mode_baseline(self, owner: str, value: dict) -> None:
        if not isinstance(owner, str) or not owner:
            return
        if owner in self._data["virtual_mode_baselines"]:
            return
        clean = _clean_virtual_mode_baseline(value)
        if clean:
            self._data["virtual_mode_baselines"][owner] = clean
            self._save()

    def remember_applied_virtual_targets(self, owner: str, targets) -> None:
        baseline = self._data["virtual_mode_baselines"].get(owner)
        clean = ip_profile.clean_target_devices(targets)
        if baseline is None or not clean:
            return
        baseline["last_applied_target_devices"] = clean
        baseline.pop("recovery_target_devices", None)
        self._save()

    def remember_virtual_target_recovery(self, owner: str, candidates) -> None:
        baseline = self._data["virtual_mode_baselines"].get(owner)
        if baseline is None:
            return
        clean = []
        for candidate in candidates if isinstance(candidates, list) else []:
            targets = ip_profile.clean_target_devices(candidate)
            if targets and targets not in clean:
                clean.append(targets)
        if clean:
            baseline["recovery_target_devices"] = clean[:4]
            self._save()

    def forget_virtual_mode_baseline(self, owner: str) -> None:
        if owner in self._data["virtual_mode_baselines"]:
            del self._data["virtual_mode_baselines"][owner]
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
            return (
                copy.deepcopy(g["buttons"])
                if g else copy.deepcopy(self._data["global"]["buttons"])
            )
        return copy.deepcopy(self._data["global"]["buttons"])

    def vibration_for(self, scope: str, appid=None) -> dict:
        if scope == "game" and appid is not None:
            g = self._game(appid)
            return (
                dict(g["vibration"])
                if g else dict(self._data["global"]["vibration"])
            )
        return dict(self._data["global"]["vibration"])

    def virtual_controller_for(self, scope: str, appid=None) -> dict:
        if scope == "game" and appid is not None:
            game = self._game(appid)
            return (
                dict(game["virtual_controller"])
                if game
                else dict(self._data["global"]["virtual_controller"])
            )
        return dict(self._data["global"]["virtual_controller"])

    def has_game(self, appid) -> bool:
        return str(appid) in self._data["games"]

    def list_games(self) -> list:
        return list(self._data["games"].keys())

    def create_game_from_global(self, appid) -> None:
        self._data["games"][str(appid)] = {
            **copy.deepcopy(self._data["global"]),
            "follow_global": False,
        }
        self._save()

    def game_profile(self, appid):
        """The game's own stored button overrides, or None if no entry."""
        g = self._game(appid)
        return copy.deepcopy(g["buttons"]) if g is not None else None

    def differs_from_global(self, appid, component=None) -> bool:
        """Whether the game's own overrides actually differ from global (a bare
        scope-toggle copies global → not 'configured')."""
        g = self._game(appid)
        if g is None:
            return False
        if component is not None:
            if component not in _COMPONENTS:
                raise ValueError(f"unknown component: {component}")
            return g[component] != self._data["global"][component]
        return any(
            g[name] != self._data["global"][name]
            for name in _COMPONENTS
        )

    def game_vibration_differs(self, appid) -> bool:
        game = self._game(appid)
        return (
            game is not None
            and game["vibration"] != self._data["global"]["vibration"]
        )

    def forget_game(self, appid) -> None:
        """Delete the game's stored remap so it reverts to global. No-op when none."""
        if str(appid) in self._data["games"]:
            del self._data["games"][str(appid)]
            self._save()

    def _profile_target(self, scope: str, appid=None) -> dict:
        """The overrides dict to mutate for a scope. Editing a game value activates
        its own profile (follow_global=False), seeded from global on first touch."""
        if scope == "global":
            return self._data["global"]
        if scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            g = self._data["games"].setdefault(
                str(appid), {
                    **copy.deepcopy(self._data["global"]),
                    "follow_global": False,
                })
            g["follow_global"] = False
            return g
        raise ValueError(f"unknown scope: {scope}")

    def replace(self, scope: str, appid, data: dict) -> None:
        tgt = self._profile_target(scope, appid)["buttons"]
        tgt.clear()
        tgt.update(_clean_buttons(data))
        self._save()

    def patch_vibration(self, scope: str, appid, patch: dict) -> None:
        clean = _clean_vibration(patch)
        if not clean:
            return
        if scope == "global":
            target = self._data["global"]["vibration"]
        elif scope == "game":
            if appid is None:
                raise ValueError("appid required for game scope")
            game = self._data["games"].setdefault(
                str(appid), {
                    **copy.deepcopy(self._data["global"]),
                    "follow_global": False,
                })
            game["follow_global"] = False
            target = game["vibration"]
        else:
            raise ValueError(f"unknown scope: {scope}")
        target.update(clean)
        self._save()

    def patch_component(
        self, component: str, patch: dict, scope: str, appid=None
    ) -> None:
        if component not in _COMPONENTS:
            raise ValueError(f"unknown component: {component}")
        if component == "vibration":
            self.patch_vibration(scope, appid, patch)
            return
        target = self._profile_target(scope, appid)[component]
        clean = (
            _clean_buttons(patch)
            if component == "buttons"
            else _clean_virtual_controller(patch)
        )
        if not clean:
            return
        target.update(clean)
        self._save()

    def reset_component(self, component: str, scope: str, appid=None) -> None:
        if component not in _COMPONENTS:
            raise ValueError(f"unknown component: {component}")
        self._profile_target(scope, appid)[component].clear()
        self._save()

    def reset(self, scope: str, appid=None) -> None:
        self.reset_component("buttons", scope, appid)

    def _save(self) -> None:
        atomic_json_save(self._path, self._data)
