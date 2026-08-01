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
from controllers.capabilities import clean_report, report
from controllers.diagnostics import IntegratedDiagnostics
from controllers.operations import OperationResult
from controllers.vibration import VibrationController


class ControllerBackend:
    """No manager present: honest empty config; writes are no-ops returning it."""

    manager = detect.NONE

    def __init__(self, version=None):
        self._version = version
        self._integrated_diagnostics = IntegratedDiagnostics()

    def _stamp(self, cfg: dict) -> dict:
        if "capabilities" not in cfg:
            cfg["capabilities"] = self.get_capabilities()
        cfg["manager"] = self.manager
        cfg["manager_version"] = self._version
        cfg["supported"] = cfg.get("kind", "none") != "none"
        return cfg

    def get_capabilities(self, appid=None) -> dict:
        return clean_report(report(None, self.manager, {}))

    def get_config(self, appid=None) -> dict:
        return self._stamp({"kind": "none"})

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        return self.get_config()

    def set_setting(self, field: str, value: str, appid=None) -> dict:
        return self.get_config(appid)

    def set_vibration(self, patch: dict, scope="global", appid=None) -> dict:
        return self.get_config(appid)

    def test_vibration(self, pattern="pulse", channel=None, strength=100):
        return {
            "sent": False,
            "stopped": False,
            "restored": True,
            "reason": "unsupported",
        }

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

    def differs_from_global(self, appid) -> bool:
        return False

    def game_vibration_differs(self, appid) -> bool:
        return False

    def forget_game(self, appid) -> None:
        pass

    def create_game_from_global(self, appid) -> None:
        pass

    def set_follow_global(self, appid, follow: bool) -> None:
        pass

    def effective_overrides(self, appid):
        return None

    def effective_profile(self, appid):
        return None

    def owns_loaded_profile(self) -> bool:
        return False

    def apply_effective(self, appid, apply_buttons=True) -> bool:
        return False

    def apply_effective_components(self, appid, apply_buttons=True) -> dict:
        applied = self.apply_effective(appid, apply_buttons)
        return {"buttons": applied, "vibration": applied}

    def _operation_result(
        self, component, status, desired, appid, generation,
        *, reason=None, actual=None, owner=None,
    ) -> OperationResult:
        return OperationResult(
            component, status, reason, owner or self.manager,
            generation, appid, desired, actual,
        )

    def apply_component(self, component, desired, appid, generation):
        if component not in {
            "virtual_controller", "buttons", "vibration",
        }:
            return self._operation_result(
                component, "unsupported", {}, appid, generation,
                reason="unsupported", owner="none",
            )
        if not desired:
            return self._operation_result(
                component, "applied", {}, appid, generation,
                actual={}, owner="none",
            )
        return self._operation_result(
            component, "unsupported", desired, appid, generation,
            reason="unsupported", owner="none",
        )

    def wait_ready(self, appid, generation) -> bool:
        return True

    def cancel_transients(self, reason) -> None:
        pass

    def clear_translated_state(self) -> bool:
        return True

    def restore_external(self) -> bool:
        return True

    def diagnostics(self) -> dict:
        return {
            "manager": self.manager,
            "manager_version": self._version,
        }

    def get_integrated_diagnostics(self) -> dict:
        manager_state = self.diagnostics()
        try:
            manager_state["capabilities"] = self.get_capabilities()
        except Exception:  # diagnostics must remain available on manager failure
            pass
        return self._integrated_diagnostics.snapshot(
            getattr(self, "_device_key", None), manager_state
        )


class IpBackend(ControllerBackend):
    """InputPlumber (SteamOS): per-button remap."""

    manager = detect.INPUTPLUMBER

    def __init__(self, store, dbus, version=None, device_key=None):
        super().__init__(version)
        self._store = store
        self._dbus = dbus
        self._device_key = device_key
        self._vibration = VibrationController(device_key, dbus)
        self._identified = bool(
            ip_profile.composite_names_for(device_key)
        )
        self._vibration_last_apply = None
        configure = getattr(self._dbus, "set_expected_names", None)
        if callable(configure):
            configure(ip_profile.composite_names_for(device_key))

    def get_config(self, appid=None) -> dict:
        config = ip.get_config(
            self._store, self._dbus, self._device_key, appid=appid,
            vibration=self._vibration,
        )
        if self._vibration_last_apply is not None:
            config["vibration"]["last_apply"] = (
                self._vibration_last_apply
            )
        return self._stamp(config)

    def get_capabilities(self, appid=None) -> dict:
        return ip.capabilities_report(
            self._dbus, self._device_key, self._vibration
        )

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        return self._stamp(
            ip.set_button(
                self._store, self._dbus, self._device_key, source, targets,
                scope, appid, vibration=self._vibration,
            ))

    def reset(self, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        return self._stamp(ip.reset(
            self._store, self._dbus, self._device_key, scope, appid,
            vibration=self._vibration,
        ))

    def set_vibration(self, patch: dict, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        config = ip.set_vibration(
            self._store, self._dbus, self._device_key, patch, scope, appid,
            vibration=self._vibration,
        )
        if "last_apply" in config.get("vibration", {}):
            self._vibration_last_apply = config["vibration"]["last_apply"]
        return self._stamp(config)

    def test_vibration(self, pattern="pulse", channel=None, strength=100):
        if not self._identified:
            return super().test_vibration(pattern, channel, strength)
        return ip.test_vibration(
            self._vibration, pattern, channel, strength
        )

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

    def game_vibration_differs(self, appid) -> bool:
        return self._store.game_vibration_differs(appid)

    def forget_game(self, appid) -> None:
        self._store.forget_game(appid)

    def create_game_from_global(self, appid) -> None:
        self._store.create_game_from_global(appid)

    def set_follow_global(self, appid, follow: bool) -> None:
        self._store.set_follow_global(appid, bool(follow))

    def effective_overrides(self, appid):
        return self._store.effective_overrides(appid)

    def effective_profile(self, appid):
        return self._store.effective_profile(appid)

    def owns_loaded_profile(self) -> bool:
        return self._store.profile_state(self._device_key) is not None

    def apply_effective(self, appid, apply_buttons=True) -> bool:
        status = self.apply_effective_components(appid, apply_buttons)
        return status["buttons"] and status["vibration"]

    def apply_effective_components(self, appid,
                                   apply_buttons=True) -> dict:
        if not self._identified:
            return {"buttons": False, "vibration": False}
        status = ip.apply_effective_components(
            self._store, self._dbus, self._device_key, appid,
            vibration=self._vibration, apply_buttons=apply_buttons,
        )
        self._vibration_last_apply = status["vibration"]
        return status

    def apply_component(self, component, desired, appid, generation):
        if component == "virtual_controller":
            if not desired:
                return self._operation_result(
                    component, "applied", {}, appid, generation,
                    actual={},
                )
            return self._operation_result(
                component, "unsupported", desired, appid, generation,
                reason="unsupported",
            )
        if not self._identified:
            return self._operation_result(
                component, "unsupported", desired, appid, generation,
                reason="unsupported",
            )
        if component == "buttons":
            applied = ip._apply_overrides(
                self._store, self._dbus, self._device_key, desired
            )
            return self._operation_result(
                component, "applied" if applied else "failed",
                desired, appid, generation,
                reason=None if applied else "apply_failed",
                actual=desired if applied else None,
            )
        if component == "vibration":
            state = self._vibration.state()
            if desired:
                ip._ensure_vibration_baseline(
                    self._store, self._dbus, self._device_key,
                    state, self._vibration,
                )
            applied = ip._apply_vibration(
                self._dbus, self._vibration, desired
            )
            exact = bool(state and state.get("readback"))
            status = (
                "applied" if applied and exact
                else "accepted_unverifiable" if applied
                else "failed"
            )
            self._vibration_last_apply = applied
            return self._operation_result(
                component, status, desired, appid, generation,
                reason=None if applied else "apply_failed",
                actual=desired if applied and exact else None,
            )
        return super().apply_component(
            component, desired, appid, generation
        )

    def wait_ready(self, appid, generation) -> bool:
        source_paths = getattr(self._dbus, "source_device_paths", None)
        if callable(source_paths):
            return bool(source_paths())
        return bool(self._dbus.capabilities())

    def cancel_transients(self, reason) -> None:
        stop = getattr(self._dbus, "stop_rumble", None)
        if callable(stop):
            stop()

    def clear_translated_state(self) -> bool:
        self.cancel_transients("clear_translated_state")
        return True

    def restore_external(self) -> bool:
        if not self._identified:
            return False
        applied = ip.restore_external(
            self._store, self._dbus, self._device_key,
            vibration=self._vibration,
        )
        self._vibration_last_apply = applied
        return applied

    def diagnostics(self) -> dict:
        dbus_diagnostics = getattr(self._dbus, "diagnostics", None)
        dbus_state = dbus_diagnostics() if callable(dbus_diagnostics) else {}
        vibration_diagnostics = getattr(
            self._vibration, "diagnostics", None
        )
        vibration_state = (
            vibration_diagnostics()
            if callable(vibration_diagnostics)
            else None
        )
        capabilities = dbus_state.get("capabilities") or []
        result = {
            **super().diagnostics(),
            "device_key": self._device_key,
            "device_known": ip_profile.is_known_device(self._device_key),
            "mapped_buttons": [
                {"source": source, "label": label}
                for source, label in ip.live_buttons(
                    self._dbus, self._device_key, capabilities
                )
            ],
            "dbus": dbus_state,
        }
        if vibration_state is not None:
            result["vibration"] = vibration_state
        return result


class HhdBackend(ControllerBackend):
    """Handheld Daemon (Bazzite): controller settings (mode + paddle behavior)."""

    manager = detect.HHD

    def __init__(self, version=None, store=None, dbus=None, device_key=None):
        super().__init__(version)
        self._store = store
        self._device_key = device_key
        self._last_vibration_operation = None
        self._vibration_last_apply = None

    def _vibration_config(self, state, appid=None, apply_status=None) -> dict:
        vibration = hhd_config.vibration_state(state, self._device_key)
        if vibration is None:
            return {
                "supported": False,
                "enabled": None,
                "test_supported": False,
            }
        desired = self._store.effective_vibration(appid)
        config = {
            **vibration,
            "supported": True,
            "test_supported": False,
            "enabled": desired.get("enabled", vibration["value"] > 0),
            "value": desired.get("value", vibration["value"]),
        }
        status = (
            self._vibration_last_apply
            if apply_status is None
            else bool(apply_status)
        )
        if status is not None:
            config["last_apply"] = status
        return config

    def _config_from_state(self, state, appid=None, apply_status=None):
        config = hhd_config.get_config(state)
        config["vibration"] = self._vibration_config(
            state, appid, apply_status
        )
        config["follows_global"] = self._store.is_following_global(appid)
        config["has_game_profile"] = self._store.has_game(appid)
        config["capabilities"] = hhd_config.capabilities_report(
            state, self._device_key, hhd_api.read_settings()
        )
        return self._stamp(config)

    def get_capabilities(self, appid=None) -> dict:
        state = hhd_api.read_state()
        return hhd_config.capabilities_report(
            state, self._device_key, hhd_api.read_settings()
        )

    def get_config(self, appid=None) -> dict:
        return self._config_from_state(hhd_api.read_state(), appid)

    def set_setting(self, field: str, value: str, appid=None) -> dict:
        payload = hhd_config.apply_setting(hhd_api.read_state(), field, value)
        if payload:
            echoed = hhd_api.post_state(payload)  # POST echoes the full merged state
            if echoed is not None:
                return self._config_from_state(echoed, appid)
        return self.get_config(appid)

    def _apply_vibration(self, desired: dict) -> bool:
        if not desired:
            return True
        state = hhd_api.read_state()
        vibration = hhd_config.vibration_state(state, self._device_key)
        if vibration is None:
            self._last_vibration_operation = {
                "owner": "hhd", "ok": False, "reason": "unsupported",
            }
            return False
        value = (
            0
            if desired.get("enabled") is False
            else desired.get("value", vibration["value"])
        )
        payload = hhd_config.vibration_payload(state, value)
        echoed = hhd_api.post_state(payload) if payload else None
        actual = hhd_config.vibration_state(echoed, self._device_key)
        ok = actual is not None and actual["value"] == value
        rollback_confirmed = None
        if not ok:
            rollback_payload = hhd_config.vibration_payload(
                state, vibration["value"]
            )
            rollback_echo = (
                hhd_api.post_state(rollback_payload)
                if rollback_payload
                else None
            )
            rollback = hhd_config.vibration_state(
                rollback_echo, self._device_key
            )
            rollback_confirmed = (
                rollback is not None
                and rollback["value"] == vibration["value"]
            )
        self._last_vibration_operation = {
            "owner": "hhd",
            "ok": ok,
            "echoed_value": actual["value"] if actual is not None else None,
            **(
                {}
                if ok
                else {
                    "reason": "config_echo_mismatch",
                    "rollback_confirmed": rollback_confirmed,
                }
            ),
        }
        return ok

    def _ensure_vibration_baseline(self, vibration) -> None:
        current = self._store.vibration_for("global")
        observed = {
            "enabled": vibration["value"] > 0,
            "value": vibration["value"],
        }
        self._store.remember_vibration_baseline(
            f"hhd:{self._device_key or ''}", observed
        )
        baseline = {
            field: value
            for field, value in observed.items()
            if field not in current
        }
        if baseline:
            self._store.patch_vibration("global", None, baseline)

    def set_vibration(self, patch: dict, scope="global", appid=None) -> dict:
        state = hhd_api.read_state()
        vibration = hhd_config.vibration_state(state, self._device_key)
        if vibration is None or not isinstance(patch, dict):
            return self.get_config(appid)
        allowed = {
            field: patch[field]
            for field in ("enabled", "value")
            if field in patch
        }
        self._ensure_vibration_baseline(vibration)
        if isinstance(allowed.get("enabled"), bool) and not allowed["enabled"]:
            current = self._store.effective_vibration(appid)
            allowed.setdefault(
                "value", current.get("value", vibration["value"])
            )
        self._store.patch_vibration(scope, appid, allowed)
        applied = self._apply_vibration(
            self._store.effective_vibration(appid)
        )
        self._vibration_last_apply = applied
        return self._config_from_state(
            hhd_api.read_state(), appid, applied
        )

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

    def game_vibration_differs(self, appid) -> bool:
        return self._store.game_vibration_differs(appid)

    def forget_game(self, appid) -> None:
        self._store.forget_game(appid)

    def create_game_from_global(self, appid) -> None:
        self._store.create_game_from_global(appid)

    def set_follow_global(self, appid, follow: bool) -> None:
        self._store.set_follow_global(appid, bool(follow))

    def effective_overrides(self, appid):
        return self._store.effective_overrides(appid)

    def effective_profile(self, appid):
        return self._store.effective_profile(appid)

    def apply_effective(self, appid, apply_buttons=True) -> bool:
        desired = self._store.effective_vibration(appid)
        if desired:
            state = hhd_api.read_state()
            vibration = hhd_config.vibration_state(
                state, self._device_key
            )
            if vibration is not None:
                self._ensure_vibration_baseline(vibration)
                desired = self._store.effective_vibration(appid)
        applied = self._apply_vibration(desired)
        self._vibration_last_apply = applied
        return applied

    def apply_effective_components(self, appid,
                                   apply_buttons=True) -> dict:
        applied = self.apply_effective(appid, apply_buttons)
        return {"buttons": True, "vibration": applied}

    def apply_component(self, component, desired, appid, generation):
        if component == "virtual_controller":
            if not desired:
                return self._operation_result(
                    component, "applied", {}, appid, generation,
                    actual={},
                )
            return self._operation_result(
                component, "unsupported", desired, appid, generation,
                reason="unsupported",
            )
        if component == "buttons":
            if not desired:
                return self._operation_result(
                    component, "applied", {}, appid, generation,
                    actual={},
                )
            return self._operation_result(
                component, "unsupported", desired, appid, generation,
                reason="unsupported",
            )
        if component == "vibration":
            applied = self._apply_vibration(desired)
            self._vibration_last_apply = applied
            return self._operation_result(
                component,
                "accepted_unverifiable" if applied else "failed",
                desired, appid, generation,
                reason=None if applied else "apply_failed",
            )
        return super().apply_component(
            component, desired, appid, generation
        )

    def wait_ready(self, appid, generation) -> bool:
        return isinstance(hhd_api.read_state(), dict)

    def restore_external(self) -> bool:
        baseline = self._store.vibration_baseline(
            f"hhd:{self._device_key or ''}"
        )
        if not baseline:
            return True
        applied = self._apply_vibration(baseline)
        self._vibration_last_apply = applied
        return applied

    def diagnostics(self) -> dict:
        result = {
            **super().diagnostics(),
            "device_key": self._device_key,
            "vibration_owner": "hhd",
        }
        if self._last_vibration_operation is not None:
            result["vibration"] = dict(self._last_vibration_operation)
        return result


def select_controller_backend(detected: dict, store, dbus, device=None) -> ControllerBackend:
    """Pick the backend for the detected manager; NullBackend-equivalent otherwise.
    Takes the whole DeviceProfile (like select_fan_backend / select_charge_limit /
    tdp select_backend); the device key drives InputPlumber's per-device button table."""
    mgr = detected.get("manager")
    version = detected.get("version")
    if mgr == detect.INPUTPLUMBER:
        return IpBackend(store, dbus, version, getattr(device, "key", None))
    if mgr == detect.HHD:
        return HhdBackend(
            version, store, dbus, getattr(device, "key", None)
        )
    return ControllerBackend(version)
