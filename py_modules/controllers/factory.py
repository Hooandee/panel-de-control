from controllers import detect
from controllers import hhd as hhd_api
from controllers import hhd_config
from controllers import inputplumber as ip
from controllers import ip_profile
from controllers.capabilities import clean_report, report, surface
from controllers.diagnostics import IntegratedDiagnostics
from controllers.operations import OperationResult
from controllers.vibration import VibrationController
from controllers.virtual_mode import (
    HhdVirtualModeAdapter,
    InputPlumberVirtualModeAdapter,
)


_VIBRATION_READBACK_FIELDS = (
    "enabled", "value", "left", "right", "intensity",
    "left_pattern", "right_pattern", "touchpad_enabled",
    "touchpad_intensity", "hd_game_enabled", "trigger_left",
    "trigger_right", "trigger_left_source", "trigger_right_source",
)


def _vibration_readback(desired, state, dbus):
    route_fields = {
        "lenovo_hd": {
            "intensity", "left_pattern", "right_pattern",
            "touchpad_enabled", "touchpad_intensity",
        },
        "asus_xbox_hd": {
            "left", "right", "hd_game_enabled", "trigger_left",
            "trigger_right", "trigger_left_source", "trigger_right_source",
        },
    }
    readable = route_fields.get(state.get("mode"), set(state)) | {"enabled"}
    actual = {}
    for field in _VIBRATION_READBACK_FIELDS:
        if field not in desired or field not in readable:
            continue
        if field == "enabled":
            read_enabled = getattr(
                dbus, "force_feedback_enabled", lambda: None
            )
            value = read_enabled()
        else:
            value = state.get(field)
        actual[field] = value
    expected = {
        field: desired[field]
        for field in _VIBRATION_READBACK_FIELDS
        if field in desired and field in readable
    }
    complete = all(
        field in readable
        for field in _VIBRATION_READBACK_FIELDS
        if field in desired
    )
    return actual, actual == expected, complete


class ControllerBackend:
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

    def set_virtual_mode(self, mode: str, scope="global", appid=None) -> dict:
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

    def game_virtual_mode(self, appid):
        return None

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
    manager = detect.INPUTPLUMBER

    def __init__(self, store, dbus, version=None, device_key=None):
        super().__init__(version)
        self._store = store
        self._dbus = dbus
        self._device_key = device_key
        vibration_owner = f"inputplumber:{device_key or ''}"
        vibration_baseline = store.vibration_baseline(vibration_owner)
        vibration_route = getattr(
            store, "vibration_route", lambda _owner: None
        )(vibration_owner)
        if vibration_route == "lenovo_hd":
            vibration_baseline = store.effective_vibration(None)
        self._vibration = VibrationController(
            device_key,
            dbus,
            lenovo_baseline=vibration_baseline,
            lenovo_route=vibration_route == "lenovo_hd",
        )
        self._virtual_mode = InputPlumberVirtualModeAdapter(
            store, dbus, device_key
        )
        self._identified = bool(
            ip_profile.composite_names_for(device_key)
        )
        self._vibration_last_apply = None
        self._virtual_mode_last_apply = None
        self._pending_virtual_mode = None
        configure = getattr(self._dbus, "set_expected_names", None)
        if callable(configure):
            configure(ip_profile.composite_names_for(device_key))

    def get_config(self, appid=None) -> dict:
        config = ip.get_config(
            self._store, self._dbus, self._device_key, appid=appid,
            vibration=self._vibration,
            virtual_mode=(self._virtual_mode if self._identified else None),
        )
        if self._vibration_last_apply is not None:
            config["vibration"]["last_apply"] = (
                self._vibration_last_apply
            )
        if self._virtual_mode_last_apply is not None:
            config["virtual_controller"]["last_apply"] = (
                self._virtual_mode_last_apply
            )
        return self._stamp(config)

    def get_capabilities(self, appid=None) -> dict:
        return ip.capabilities_report(
            self._dbus, self._device_key, self._vibration,
            self._virtual_mode if self._identified else None,
        )

    def set_button(self, source: str, targets: list, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        return self._stamp(
            ip.set_button(
                self._store, self._dbus, self._device_key, source, targets,
                scope, appid, vibration=self._vibration,
                virtual_mode=self._virtual_mode,
            ))

    def reset(self, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        return self._stamp(ip.reset(
            self._store, self._dbus, self._device_key, scope, appid,
            vibration=self._vibration,
            virtual_mode=self._virtual_mode,
        ))

    def set_vibration(self, patch: dict, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        config = ip.set_vibration(
            self._store, self._dbus, self._device_key, patch, scope, appid,
            vibration=self._vibration,
            virtual_mode=self._virtual_mode,
        )
        if "last_apply" in config.get("vibration", {}):
            self._vibration_last_apply = config["vibration"]["last_apply"]
        return self._stamp(config)

    def set_virtual_mode(self, mode: str, scope="global", appid=None) -> dict:
        if not self._identified:
            return self.get_config(appid)
        config = self._virtual_mode.config(appid)
        if not config["supported"] or mode not in config["options"]:
            return self.get_config(appid)
        self._store.patch_component(
            "virtual_controller", {"mode": mode}, scope, appid
        )
        return self.get_config(appid)

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

    def game_virtual_mode(self, appid):
        return self._store.virtual_controller_for("game", appid).get("mode")

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
        return self._identified and (
            self._store.profile_state(self._device_key) is not None
            or bool(self._store.virtual_mode_baseline(
                f"inputplumber:{self._device_key or ''}"
            ))
        )

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
        if not self._identified:
            return super().apply_component(
                component, desired, appid, generation
            )
        if component == "virtual_controller":
            baseline = self._store.virtual_mode_baseline(
                f"inputplumber:{self._device_key or ''}"
            )
            mode = desired.get("mode") if desired else (
                "auto" if baseline else None
            )
            if mode is None:
                self._pending_virtual_mode = None
                return self._operation_result(
                    component, "applied", {}, appid, generation,
                    actual={},
                )
            result = self._virtual_mode.apply(mode)
            applied = result["accepted"]
            ready = result["ready"]
            rollback = result["rollback_confirmed"]
            self._virtual_mode_last_apply = applied and ready
            self._pending_virtual_mode = bool(applied and not ready)
            status = (
                "applied" if ready
                else "accepted_unverifiable" if applied
                else "failed" if rollback
                else "recovery_required"
            )
            return self._operation_result(
                component, status,
                desired, appid, generation,
                reason=(
                    None if applied
                    else "profile_conflict"
                    if result.get("reason") == "profile_conflict"
                    else "unsupported"
                    if result.get("reason") in {
                        "capability_unavailable", "unsupported_mode"
                    }
                    else "apply_failed"
                ),
                actual=(
                    {"mode": result["actual"]}
                    if result.get("actual") else None
                ),
            )
        if component == "buttons":
            applied = ip._apply_overrides(
                self._store, self._dbus, self._device_key, desired,
            )
            return self._operation_result(
                component, "applied" if applied else "failed",
                desired, appid, generation,
                reason=None if applied else "apply_failed",
                actual=desired if applied else None,
            )
        if component == "vibration":
            state = self._vibration.state()
            native_requested = ip._native_vibration_requested(desired)
            baseline_ready = True
            if desired:
                baseline_ready = ip._ensure_vibration_baseline(
                    self._store, self._dbus, self._device_key,
                    state, self._vibration,
                    prepare_native=native_requested,
                )
            enabled_applied, native_applied = (
                ip._apply_vibration_parts(
                    self._dbus, self._vibration, desired,
                    apply_native=native_requested,
                )
                if baseline_ready else (False, False)
            )
            post_state = (
                self._vibration.state()
                if enabled_applied and native_applied else None
            )
            exact = bool(post_state and post_state.get("readback"))
            actual, readback_matches, readback_complete = (
                _vibration_readback(desired, post_state, self._dbus)
                if exact else (None, True, False)
            )
            native_confirmed = native_applied and readback_matches
            route_recovered = ip._finish_vibration_route(
                self._store, self._device_key,
                state if baseline_ready and native_requested else None,
                self._vibration, native_confirmed, appid,
            )
            applied = enabled_applied and native_confirmed and route_recovered
            native_diagnostics = getattr(
                self._vibration, "diagnostics", lambda: {}
            )() or {}
            recovery_required = not applied and (
                native_diagnostics.get("rollback_confirmed") is False
                or not route_recovered
            )
            status = (
                "applied" if applied and exact and readback_complete
                else "accepted_unverifiable" if applied
                else "recovery_required" if recovery_required
                else "failed"
            )
            self._vibration_last_apply = applied
            return self._operation_result(
                component, status, desired, appid, generation,
                reason=(
                    None if applied
                    else "readback_mismatch"
                    if exact and not readback_matches
                    else "restore_failed" if recovery_required
                    else "apply_failed"
                ),
                actual=actual if exact else None,
            )
        return super().apply_component(
            component, desired, appid, generation
        )

    def wait_ready(self, appid, generation) -> bool:
        if self._pending_virtual_mode:
            self._pending_virtual_mode = False
            outcome = self._virtual_mode.wait_ready()
            actual = outcome.get("actual")
            if outcome["ready"]:
                self._virtual_mode_last_apply = True
                return self._operation_result(
                    "virtual_controller", "applied",
                    self._store.effective_virtual_controller(appid),
                    appid, generation,
                    actual={"mode": actual},
                )
            self._virtual_mode_last_apply = False
            return self._operation_result(
                "virtual_controller",
                (
                    "failed" if outcome["rollback_confirmed"]
                    else "recovery_required"
                ),
                self._store.effective_virtual_controller(appid),
                appid, generation,
                reason=(
                    "device_not_ready"
                    if outcome["rollback_confirmed"] else "restore_failed"
                ),
                actual={"mode": actual} if actual is not None else None,
            )
        source_paths = getattr(self._dbus, "source_device_paths", None)
        if callable(source_paths):
            return bool(source_paths())
        return bool(self._dbus.capabilities())

    def cancel_transients(self, reason) -> None:
        self._virtual_mode.cancel()
        self._pending_virtual_mode = False
        stop = getattr(self._dbus, "stop_rumble", None)
        if callable(stop):
            stop()

    def clear_translated_state(self) -> bool:
        self.cancel_transients("clear_translated_state")
        return True

    def restore_external(self) -> bool:
        if not self._identified:
            return False
        virtual_applied = self._virtual_mode.restore_external()
        applied = ip.restore_external(
            self._store, self._dbus, self._device_key,
            vibration=self._vibration,
        )
        self._vibration_last_apply = applied
        self._virtual_mode_last_apply = virtual_applied
        return virtual_applied and applied

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
        if self._identified:
            virtual = self._virtual_mode.config()
            if virtual["supported"]:
                result["virtual_controller"] = virtual
        if vibration_state is not None:
            result["vibration"] = vibration_state
        return result


class HhdBackend(ControllerBackend):
    manager = detect.HHD

    def __init__(self, version=None, store=None, dbus=None, device_key=None,
                 vibration=None):
        super().__init__(version)
        self._store = store
        self._device_key = device_key
        self._vibration = vibration or VibrationController(device_key, None)
        self._last_vibration_operation = None
        self._vibration_last_apply = None
        self._virtual_mode = HhdVirtualModeAdapter(
            store,
            device_key,
            hhd_api.read_state,
            hhd_api.read_settings,
            hhd_api.post_state,
        )
        self._pending_virtual_mode = None
        self._last_virtual_mode_apply = None

    def _xbox_native_state(self):
        if self._device_key != "rog_xbox_ally_x":
            return None
        state = self._vibration.state()
        if state is None or state.get("mode") != "asus_xbox_hd":
            return None
        return state

    def _virtual_mode_config(self, state, settings, appid=None) -> dict:
        capabilities = self._virtual_mode.capabilities(state, settings)
        if capabilities is None:
            return {
                "supported": False,
                "mode": "auto",
                "actual_mode": hhd_config.get_config(state).get("mode"),
                "options": [],
                "scope": [],
            }
        desired = self._store.effective_virtual_controller(appid)
        config = {
            "supported": True,
            "mode": desired.get("mode", "auto"),
            "actual_mode": capabilities["current"],
            "options": capabilities["options"],
            "scope": capabilities["scope"],
            "readiness": capabilities["readiness"],
        }
        if self._last_virtual_mode_apply is not None:
            config["last_apply"] = self._last_virtual_mode_apply
        return config

    def _vibration_config(self, state, appid=None, apply_status=None) -> dict:
        vibration = hhd_config.vibration_state(state, self._device_key)
        if vibration is None:
            return {
                "supported": False,
                "enabled": None,
                "test_supported": False,
            }
        native = self._xbox_native_state()
        desired = self._store.effective_vibration(appid)
        config = {
            **vibration,
            "supported": True,
            "test_supported": False,
            "enabled": desired.get("enabled", vibration["value"] > 0),
            "value": desired.get("value", vibration["value"]),
        }
        if native is not None:
            capabilities = self._vibration.capabilities() or {}
            test = capabilities.get("test", {})
            config.update(native)
            config.update({
                "left": desired.get("left", native["left"]),
                "right": desired.get("right", native["right"]),
                "actual_left": native["left"],
                "actual_right": native["right"],
                "confirmation": capabilities.get("readback", "driver"),
                "test_supported": bool(
                    test.get("patterns") and test.get("channels")
                ),
                "test_patterns": list(test.get("patterns", [])),
                "test_channels": list(test.get("channels", [])),
                "base_owner": "hhd",
                "enhancement_owner": "panel",
            })
        status = (
            self._vibration_last_apply
            if apply_status is None
            else bool(apply_status)
        )
        if status is not None:
            config["last_apply"] = status
        return config

    def _config_from_state(self, state, appid=None, apply_status=None):
        settings = hhd_api.read_settings()
        config = hhd_config.get_config(state)
        config["virtual_controller"] = self._virtual_mode_config(
            state, settings, appid
        )
        config["vibration"] = self._vibration_config(
            state, appid, apply_status
        )
        config["follows_global"] = self._store.is_following_global(appid)
        config["has_game_profile"] = self._store.has_game(appid)
        config["capabilities"] = self._capabilities_from_state(
            state, settings
        )
        return self._stamp(config)

    def _capabilities_from_state(self, state, settings):
        capabilities = hhd_config.capabilities_report(
            state, self._device_key, settings
        )
        if hhd_config.vibration_state(state, self._device_key) is None:
            return capabilities
        native = self._xbox_native_state()
        if native is None:
            return capabilities
        native_capabilities = self._vibration.capabilities()
        if not isinstance(native_capabilities, dict):
            return capabilities
        capabilities["surfaces"]["vibration"] = surface(
            "hhd+panel",
            "experimental",
            fields={
                **native_capabilities,
                "base_owner": "hhd",
                "enhancement_owner": "panel",
            },
            scope=("global", "game"),
            apply="hot",
            readback="exact",
            evidence="upstream",
        )
        return clean_report(capabilities)

    def get_capabilities(self, appid=None) -> dict:
        state = hhd_api.read_state()
        return self._capabilities_from_state(
            state, hhd_api.read_settings()
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

    def set_virtual_mode(self, mode: str, scope="global", appid=None) -> dict:
        capabilities = self._virtual_mode.capabilities()
        if (
            capabilities is None
            or mode not in capabilities["options"]
        ):
            return self.get_config(appid)
        self._store.patch_component(
            "virtual_controller", {"mode": mode}, scope, appid
        )
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
        value = self._desired_hhd_vibration(desired, vibration)
        actual = self._post_hhd_vibration(state, value)
        base_ok = actual is not None and actual["value"] == value
        native = self._xbox_native_state()
        native_intent = (
            self._device_key == "rog_xbox_ally_x"
            and any(
                field in desired
                for field in ("left", "right", "native_left", "native_right")
            )
        )
        native_ok = (
            self._apply_xbox_vibration(desired, native, native_intent)
            if base_ok else True
        )
        ok = base_ok and native_ok
        rollback_confirmed = None
        if not ok:
            base_rollback = self._restore_hhd_vibration(state, vibration)
            native_diagnostics = getattr(
                self._vibration, "diagnostics", lambda: None
            )() or {}
            native_rollback = (
                native_diagnostics.get("rollback_confirmed", True)
                if base_ok and native_intent and not native_ok else True
            )
            rollback_confirmed = base_rollback and native_rollback
        self._last_vibration_operation = {
            "owner": "hhd+panel" if native is not None else "hhd",
            "ok": ok,
            "echoed_value": actual["value"] if actual is not None else None,
            **(
                {}
                if ok
                else {
                    "reason": (
                        "native_unavailable"
                        if native_intent and native is None
                        else "config_echo_mismatch"
                        if not base_ok
                        else "native_apply_failed"
                    ),
                    "rollback_confirmed": rollback_confirmed,
                }
            ),
        }
        return ok

    @staticmethod
    def _desired_hhd_vibration(desired, current):
        if desired.get("enabled") is False:
            return 0
        return desired.get("value", current["value"])

    @staticmethod
    def _native_baseline_requested(desired):
        return all(
            field in desired for field in ("native_left", "native_right")
        )

    def _post_hhd_vibration(self, state, value):
        payload = hhd_config.vibration_payload(state, value)
        echoed = hhd_api.post_state(payload) if payload else None
        return hhd_config.vibration_state(echoed, self._device_key)

    def _restore_hhd_vibration(self, state, baseline):
        restored = self._post_hhd_vibration(state, baseline["value"])
        return restored is not None and restored["value"] == baseline["value"]

    def _apply_xbox_vibration(self, desired, native, requested):
        if not requested:
            return True
        if native is None:
            return False
        if self._native_baseline_requested(desired):
            return self._vibration.restore_baseline(desired)
        return self._vibration.apply({
            "left": desired.get("left", native["left"]),
            "right": desired.get("right", native["right"]),
        })

    def _ensure_vibration_baseline(self, vibration) -> None:
        current = self._store.vibration_for("global")
        observed = {
            "enabled": vibration["value"] > 0,
            "value": vibration["value"],
        }
        native = self._xbox_native_state()
        if native is not None:
            observed.update({
                "left": native["left"],
                "right": native["right"],
            })
            captured = self._vibration.capture_baseline()
            if isinstance(captured, dict):
                observed.update(captured)
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
            for field in ("enabled", "value", "left", "right")
            if field in patch
        }
        self._ensure_vibration_baseline(vibration)
        if isinstance(allowed.get("enabled"), bool) and not allowed["enabled"]:
            current = self._store.effective_vibration(appid)
            allowed.setdefault(
                "value", current.get(
                    "value", vibration["value"]
                )
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

    def game_virtual_mode(self, appid):
        return self._store.virtual_controller_for("game", appid).get("mode")

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
        return bool(self._store.virtual_mode_baseline(
            f"hhd:{self._device_key or ''}"
        ))

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
            baseline = self._store.virtual_mode_baseline(
                f"hhd:{self._device_key or ''}"
            )
            mode = desired.get("mode") if desired else (
                "auto" if baseline else None
            )
            if mode is None:
                self._pending_virtual_mode = None
                return self._operation_result(
                    component, "applied", {}, appid, generation,
                    actual={},
                )
            result = self._virtual_mode.apply(mode)
            confirmed = result["config_confirmed"]
            rollback = result["rollback_confirmed"]
            self._last_virtual_mode_apply = confirmed
            self._pending_virtual_mode = (
                mode if confirmed else None
            )
            status = (
                "accepted_unverifiable" if confirmed
                else "failed" if rollback
                else "recovery_required"
            )
            return self._operation_result(
                component, status, desired, appid, generation,
                reason=(
                    None if confirmed
                    else "profile_conflict"
                    if result.get("reason") == "profile_conflict"
                    else "readback_mismatch" if rollback
                    else "restore_failed"
                ),
                actual=(
                    {"mode": result["actual"].get("mode")}
                    if confirmed else None
                ),
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
            recovery_required = bool(
                not applied
                and (self._last_vibration_operation or {}).get(
                    "rollback_confirmed"
                ) is False
            )
            return self._operation_result(
                component,
                "accepted_unverifiable" if applied
                else "recovery_required" if recovery_required
                else "failed",
                desired, appid, generation,
                reason=None if applied
                else "restore_failed" if recovery_required
                else "apply_failed",
            )
        return super().apply_component(
            component, desired, appid, generation
        )

    def wait_ready(self, appid, generation) -> bool:
        if self._pending_virtual_mode is None:
            return isinstance(hhd_api.read_state(), dict)
        mode = self._pending_virtual_mode
        ready = self._virtual_mode.wait_ready(mode)
        self._pending_virtual_mode = None
        if ready:
            return self._operation_result(
                "virtual_controller", "applied", {"mode": mode},
                appid, generation, actual={"mode": mode},
            )
        restored = self._virtual_mode.rollback_last()
        return self._operation_result(
            "virtual_controller",
            "failed" if restored else "recovery_required",
            {"mode": mode}, appid, generation,
            reason="device_not_ready" if restored else "restore_failed",
        )

    def restore_external(self) -> bool:
        mode_baseline = self._store.virtual_mode_baseline(
            f"hhd:{self._device_key or ''}"
        )
        mode_applied = True
        if mode_baseline:
            mode_applied = self._virtual_mode.apply("auto")[
                "config_confirmed"
            ]
        baseline = self._store.vibration_baseline(
            f"hhd:{self._device_key or ''}"
        )
        if not baseline:
            return mode_applied
        applied = self._apply_vibration(baseline)
        self._vibration_last_apply = applied
        return mode_applied and applied

    def test_vibration(self, pattern="pulse", channel=None, strength=100):
        base = hhd_config.vibration_state(
            hhd_api.read_state(), self._device_key
        )
        native = self._xbox_native_state()
        if base is None or native is None:
            return super().test_vibration(pattern, channel, strength)
        return self._vibration.test(pattern, channel, strength)

    def diagnostics(self) -> dict:
        result = {
            **super().diagnostics(),
            "device_key": self._device_key,
            "vibration_owner": (
                "hhd+panel"
                if self._xbox_native_state() is not None else "hhd"
            ),
        }
        if self._last_vibration_operation is not None:
            result["vibration"] = dict(self._last_vibration_operation)
        return result


def select_controller_backend(detected: dict, store, dbus, device=None) -> ControllerBackend:
    mgr = detected.get("manager")
    version = detected.get("version")
    if mgr == detect.INPUTPLUMBER:
        return IpBackend(store, dbus, version, getattr(device, "key", None))
    if mgr == detect.HHD:
        return HhdBackend(
            version, store, dbus, getattr(device, "key", None)
        )
    return ControllerBackend(version)
