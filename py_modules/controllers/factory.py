"""One controller backend per device, mirroring tdp/factory.select_backend.

The two daemons (Handheld Daemon on Bazzite, InputPlumber on SteamOS) offer
different config surfaces, so each backend returns a discriminated `get_config`
(`kind: "remap" | "settings" | "none"`). main.py holds ONE `self._controller_backend`
and every RPC is a one-line delegation — no per-manager if/elif in the RPCs. Each
backend stamps `manager` / `manager_version` / `supported` onto its config so the
frontend needs a single round-trip.
"""
from controllers import detect
from controllers import hhd as hhd_api
from controllers import hhd_config
from controllers import inputplumber as ip
from controllers import ip_profile
from controllers.ayaneo3 import HhdMagicModules, UnavailableMagicModules


class ControllerBackend:
    """No manager present: honest empty config; writes are no-ops returning it."""

    manager = detect.NONE

    def __init__(self, version=None, actions=None):
        self._version = version
        self._actions = actions
        self._last_action = None

    def _stamp(self, cfg: dict) -> dict:
        cfg["manager"] = self.manager
        cfg["manager_version"] = self._version
        cfg["supported"] = cfg.get("kind", "none") != "none"
        if self._actions is not None:
            cfg["magic_modules"] = self._actions.state()
        return cfg

    def get_config(self, appid=None) -> dict:
        return self._stamp({"kind": "none"})

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        return self.get_config()

    def set_setting(self, field: str, value: str) -> dict:
        return self.get_config()

    def reset(self, scope="global", appid=None) -> dict:
        return self.get_config()

    def run_action(self, action: str) -> dict:
        if self._actions is not None:
            result = self._actions.run(action)
        else:
            result = {
                "action": action,
                "outcome": "unavailable",
                "accepted": None,
                "reason": "controller_action_not_supported",
            }
        self._last_action = dict(result)
        return result

    # Per-game scope: only InputPlumber (we own its remap store). No-ops elsewhere so
    # main.py can call uniformly. `effective_overrides` returning None means "not a
    # per-game backend" → the game-change re-apply skips it.
    def has_game(self, appid) -> bool:
        return False

    def is_following_global(self, appid) -> bool:
        return True

    def list_games(self) -> list:
        return []

    def game_profile(self, appid):
        return None

    def differs_from_global(self, appid) -> bool:
        return False

    def forget_game(self, appid) -> None:
        pass

    def create_game_from_global(self, appid) -> None:
        pass

    def set_follow_global(self, appid, follow: bool) -> None:
        pass

    def effective_overrides(self, appid):
        return None

    def apply_effective(self, appid) -> bool:
        return False

    def diagnostics(self) -> dict:
        diagnostics = {
            "manager": self.manager,
            "manager_version": self._version,
        }
        if self._actions is not None:
            diagnostics["magic_modules"] = self._actions.state()
            diagnostics["last_action"] = self._last_action
        return diagnostics


class IpBackend(ControllerBackend):
    """InputPlumber (SteamOS): per-button remap."""

    manager = detect.INPUTPLUMBER

    def __init__(self, store, dbus, version=None, device_key=None, actions=None):
        super().__init__(version, actions)
        self._store = store
        self._dbus = dbus
        self._device_key = device_key

    def get_config(self, appid=None) -> dict:
        return self._stamp(ip.get_config(self._store, self._dbus, self._device_key, appid=appid))

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        return self._stamp(
            ip.set_button(self._store, self._dbus, self._device_key, source, targets, scope, appid))

    def reset(self, scope="global", appid=None) -> dict:
        return self._stamp(ip.reset(self._store, self._dbus, self._device_key, scope, appid))

    def has_game(self, appid) -> bool:
        return self._store.has_game(appid)

    def is_following_global(self, appid) -> bool:
        return self._store.is_following_global(appid)

    def list_games(self) -> list:
        return self._store.list_games()

    def game_profile(self, appid):
        return self._store.game_profile(appid)

    def differs_from_global(self, appid) -> bool:
        return self._store.differs_from_global(appid)

    def forget_game(self, appid) -> None:
        self._store.forget_game(appid)

    def create_game_from_global(self, appid) -> None:
        self._store.create_game_from_global(appid)

    def set_follow_global(self, appid, follow: bool) -> None:
        self._store.set_follow_global(appid, bool(follow))

    def effective_overrides(self, appid):
        return self._store.effective_overrides(appid)

    def apply_effective(self, appid) -> bool:
        return ip.apply_effective(self._store, self._dbus, appid)

    def diagnostics(self) -> dict:
        dbus_diagnostics = getattr(self._dbus, "diagnostics", None)
        dbus_state = dbus_diagnostics() if callable(dbus_diagnostics) else {}
        capabilities = dbus_state.get("capabilities") or []
        return {
            **super().diagnostics(),
            "device_key": self._device_key,
            "device_known": ip_profile.is_known_device(self._device_key),
            "mapped_buttons": [
                {"source": source, "label": label}
                for source, label in ip_profile.buttons_for(
                    self._device_key, capabilities
                )
            ],
            "dbus": dbus_state,
        }


class HhdBackend(ControllerBackend):
    """Handheld Daemon (Bazzite): controller settings (mode + paddle behavior)."""

    manager = detect.HHD

    def __init__(self, version=None, actions=None, root="/"):
        super().__init__(version, actions)
        self._root = root

    def get_config(self, appid=None) -> dict:
        return self._stamp(hhd_config.get_config(hhd_api.read_state(self._root)))

    def set_setting(self, field: str, value: str) -> dict:
        payload = hhd_config.apply_setting(hhd_api.read_state(self._root), field, value)
        if payload:
            echoed = hhd_api.post_state(payload, self._root)  # POST echoes the full merged state
            if echoed is not None:
                return self._stamp(hhd_config.get_config(echoed))
        return self.get_config()


def select_controller_backend(
    detected: dict,
    store,
    dbus,
    device=None,
    root="/",
) -> ControllerBackend:
    """Pick the backend for the detected manager; NullBackend-equivalent otherwise.
    Takes the whole DeviceProfile (like select_fan_backend / select_charge_limit /
    tdp select_backend); the device key drives InputPlumber's per-device button table."""
    mgr = detected.get("manager")
    version = detected.get("version")
    device_key = getattr(device, "key", None)
    actions = None
    if device_key == "ayaneo_3":
        actions = UnavailableMagicModules()
        if mgr == detect.HHD:
            actions = HhdMagicModules(
                read_state=lambda: hhd_api.read_state(
                    root,
                    timeout=0.5,
                    language="en",
                ),
                post_state=lambda payload: hhd_api.post_state(
                    payload,
                    root,
                    timeout=0.5,
                ),
            )
    if mgr == detect.INPUTPLUMBER:
        return IpBackend(store, dbus, version, device_key, actions)
    if mgr == detect.HHD:
        return HhdBackend(version, actions, root)
    return ControllerBackend(version, actions)
