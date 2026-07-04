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

    def get_config(self) -> dict:
        return self._stamp({"kind": "none"})

    def set_button(self, source: str, targets: list) -> dict:
        return self.get_config()

    def set_setting(self, field: str, value: str) -> dict:
        return self.get_config()

    def reset(self) -> dict:
        return self.get_config()


class IpBackend(ControllerBackend):
    """InputPlumber (SteamOS): per-button remap."""

    manager = detect.INPUTPLUMBER

    def __init__(self, store, dbus, version=None, device_key=None):
        super().__init__(version)
        self._store = store
        self._dbus = dbus
        self._device_key = device_key

    def get_config(self) -> dict:
        return self._stamp(ip.get_config(self._store, self._dbus, self._device_key))

    def set_button(self, source: str, targets: list) -> dict:
        return self._stamp(ip.set_button(self._store, self._dbus, self._device_key, source, targets))

    def reset(self) -> dict:
        return self._stamp(ip.reset(self._store, self._dbus, self._device_key))


class HhdBackend(ControllerBackend):
    """Handheld Daemon (Bazzite): controller settings (mode + paddle behavior)."""

    manager = detect.HHD

    def get_config(self) -> dict:
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
