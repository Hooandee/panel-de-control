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


class ControllerBackend:
    """No manager present: honest empty config; writes are no-ops returning it."""

    manager = detect.NONE

    def __init__(self, version=None):
        self._version = version

    def _stamp(self, cfg: dict) -> dict:
        cfg["manager"] = self.manager
        cfg["manager_version"] = self._version
        cfg["supported"] = cfg.get("kind", "none") != "none"
        return cfg

    def get_config(self, appid=None) -> dict:
        return self._stamp({"kind": "none"})

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        return self.get_config()

    def set_setting(self, field: str, value: str) -> dict:
        return self.get_config()

    def reset(self, scope="global", appid=None) -> dict:
        return self.get_config()

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


class IpBackend(ControllerBackend):
    """InputPlumber (SteamOS): per-button remap."""

    manager = detect.INPUTPLUMBER

    def __init__(self, store, dbus, version=None, device_key=None):
        super().__init__(version)
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


class HhdBackend(ControllerBackend):
    """Handheld Daemon (Bazzite): controller settings (mode + paddle behavior)."""

    manager = detect.HHD

    def get_config(self, appid=None) -> dict:
        return self._stamp(hhd_config.get_config(hhd_api.read_state()))

    def set_setting(self, field: str, value: str) -> dict:
        payload = hhd_config.apply_setting(hhd_api.read_state(), field, value)
        if payload:
            echoed = hhd_api.post_state(payload)  # POST echoes the full merged state
            if echoed is not None:
                return self._stamp(hhd_config.get_config(echoed))
        return self.get_config()


def select_controller_backend(detected: dict, store, dbus, device=None) -> ControllerBackend:
    """Pick the backend for the detected manager; NullBackend-equivalent otherwise.
    Takes the whole DeviceProfile (like select_fan_backend / select_charge_limit /
    tdp select_backend); the device key drives InputPlumber's per-device button table."""
    mgr = detected.get("manager")
    version = detected.get("version")
    if mgr == detect.INPUTPLUMBER:
        return IpBackend(store, dbus, version, getattr(device, "key", None))
    if mgr == detect.HHD:
        return HhdBackend(version)
    return ControllerBackend(version)
