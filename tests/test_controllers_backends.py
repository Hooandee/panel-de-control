from controllers import hhd_config, inputplumber
from controllers.store import RemapStore


def _store(tmp_path, data=None):
    """A real (file-backed) RemapStore, optionally seeded with a raw dict."""
    import json
    p = tmp_path / "remap.json"
    if data is not None:
        p.write_text(json.dumps(data))
    return RemapStore(str(p))


class FakeDbus:
    """Emulates a device exposing two paddles + a quick-access button."""

    def __init__(self, caps=None):
        self._caps = caps or [
            "Gamepad:Button:South", "Gamepad:Button:LeftPaddle1",
            "Gamepad:Button:RightPaddle1", "Gamepad:Button:QuickAccess",
        ]
        self.loaded = None
        self.reset_called = False
        self._profile = "version: 1\nkind: DeviceProfile\nname: Default\nmapping: []\n"
        self.ff_enabled = True
        self.rumbled = None
        self.profile_apply = None

    def capabilities(self):
        return list(self._caps)

    def get_profile_yaml(self):
        return self._profile

    def load_profile_yaml(self, yaml):
        self.loaded = yaml
        self._profile = yaml
        return True

    def reset_default(self):
        self.reset_called = True
        return True

    def force_feedback_enabled(self):
        return self.ff_enabled

    def set_force_feedback_enabled(self, enabled):
        self.ff_enabled = bool(enabled)
        return True

    def rumble(self, strength):
        self.rumbled = strength
        return True

    def stop_rumble(self):
        self.rumbled = 0
        return True

    def source_device_paths(self):
        return []

    def record_profile_apply(self, ok, reason=None, **details):
        self.profile_apply = {
            "ok": bool(ok),
            **({} if reason is None else {"reason": reason}),
            **details,
        }

    def profile_apply_status(self):
        return self.profile_apply


class FakeVibration:
    def __init__(self, state=None, applies=True):
        self._state = state
        self.applies = applies
        self.applied = None

    def state(self):
        return dict(self._state) if self._state is not None else None

    def apply(self, patch):
        self.applied = dict(patch)
        return self.applies


class InvalidatingDbus(FakeDbus):
    def __init__(self):
        super().__init__(caps=["Gamepad:Button:LeftPaddle1"])
        self.capability_reads = 0

    def capabilities(self):
        self.capability_reads += 1
        return (
            ["Gamepad:Button:LeftPaddle1"]
            if self.capability_reads == 1
            else []
        )

    def reset_default(self):
        self.reset_called = True
        return False

    def load_profile_yaml(self, yaml):
        self.loaded = yaml
        return False


class IgnoringProfileLoadDbus(FakeDbus):
    def load_profile_yaml(self, yaml):
        self.loaded = yaml
        return True


class UnrecoverableProfileLoadDbus(FakeDbus):
    def __init__(self):
        super().__init__()
        self.load_count = 0

    def load_profile_yaml(self, yaml):
        self.load_count += 1
        self.loaded = yaml
        if self.load_count == 1:
            self._profile = "unexpected-yaml"
            return True
        return False


# ---- InputPlumber backend --------------------------------------------------

CLAW = "msi_claw_8_ai_plus"  # caps LeftPaddle1/RightPaddle1 → silkscreen M2/M1


_MERGE = lambda baseline, overrides: ("merged-yaml" if overrides else baseline)  # noqa: E731


def test_ip_get_config_lists_device_buttons_with_silkscreen_labels(tmp_path):
    cfg = inputplumber.get_config(_store(tmp_path), FakeDbus(), CLAW)
    assert cfg["kind"] == "remap"
    assert cfg["device_known"] is True
    # Per-device table order; the Claw's two grips carry real silkscreen labels.
    assert [(b["source"], b["label"]) for b in cfg["buttons"]] == [
        ("RightPaddle1", "M1"), ("LeftPaddle1", "M2"),
    ]
    # Untouched buttons have no override yet.
    assert all(b["target"] is None for b in cfg["buttons"])
    assert "South" in cfg["gamepad_targets"] and "KeyEsc" in cfg["key_targets"]
    # No game → follows global, no own profile.
    assert cfg["follows_global"] is True and cfg["has_game_profile"] is False


def test_ip_get_config_unknown_device_has_no_buttons_but_stays_honest(tmp_path):
    cfg = inputplumber.get_config(_store(tmp_path), FakeDbus(), "unknown_device")
    assert cfg["kind"] == "remap"
    assert cfg["device_known"] is False
    assert cfg["buttons"] == []


def test_ip_get_config_lists_xbox_ally_macro_buttons(tmp_path):
    dbus = FakeDbus(caps=[
        "Gamepad:Button:LeftPaddle2",
        "Gamepad:Button:RightPaddle2",
    ])

    cfg = inputplumber.get_config(
        _store(tmp_path),
        dbus,
        "rog_xbox_ally",
    )

    assert [(button["source"], button["label"]) for button in cfg["buttons"]] == [
        ("LeftPaddle2", "M2"),
        ("RightPaddle2", "M1"),
    ]


def test_ip_config_exposes_force_feedback_without_fake_strength(tmp_path):
    cfg = inputplumber.get_config(_store(tmp_path), FakeDbus(), CLAW)
    assert cfg["vibration"] == {
        "supported": True,
        "enabled": True,
        "test_supported": True,
        "test_patterns": ["pulse"],
        "test_channels": ["both"],
        "confirmation": "none",
    }


def test_ip_config_exposes_persistent_dual_motor_profile(tmp_path):
    store = _store(tmp_path)
    store.patch_vibration(
        "game", "1234", {"left": 35, "right": 45}
    )
    vibration = FakeVibration({
        "mode": "dual", "persistent": True, "left": 100, "right": 80,
        "min": 0, "max": 100, "step": 5, "readback": True,
    })

    cfg = inputplumber.get_config(
        store, FakeDbus(), CLAW, appid="1234", vibration=vibration
    )

    assert cfg["vibration"]["mode"] == "dual"
    assert cfg["vibration"]["left"] == 35
    assert cfg["vibration"]["right"] == 45
    assert cfg["vibration"]["actual_left"] == 100
    assert cfg["vibration"]["actual_right"] == 80
    assert cfg["vibration"]["persistent"] is True


def test_ip_vibration_enabled_is_per_game(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    cfg = inputplumber.set_vibration(
        store, dbus, CLAW, {"enabled": False}, scope="game", appid="1234"
    )
    assert store.effective_vibration("1234") == {"enabled": False}
    assert dbus.ff_enabled is False
    assert cfg["vibration"]["enabled"] is False


def test_ip_vibration_failure_keeps_per_game_intent_for_retry(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    vibration = FakeVibration(
        {
            "mode": "gain", "persistent": True, "value": None,
            "min": 0, "max": 100, "step": 5, "readback": False,
        },
        applies=False,
    )
    cfg = inputplumber.set_vibration(
        store, dbus, CLAW, {"value": 40}, scope="game", appid="42",
        vibration=vibration,
    )
    assert store.effective_vibration("42") == {
        "enabled": True, "value": 40,
    }
    assert cfg["vibration"]["value"] == 40
    assert cfg["vibration"]["last_apply"] is False


def test_ip_apply_effective_reapplies_persistent_gain(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.patch_vibration("game", "42", {"value": 65})
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    assert inputplumber.apply_effective(
        store, dbus, CLAW, "42", vibration=vibration, merge=_MERGE
    ) is True
    assert vibration.applied == {"value": 65}


def test_ip_vibration_only_game_change_does_not_reload_button_profile(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.patch_vibration("game", "42", {"value": 65})
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    assert inputplumber.apply_effective(
        store, dbus, CLAW, "42", vibration=vibration,
        apply_buttons=False, merge=_MERGE
    ) is True
    assert dbus.loaded is None
    assert vibration.applied == {"value": 65}


def test_ip_game_vibration_captures_global_baseline_for_handoff(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    inputplumber.set_vibration(
        store, dbus, CLAW, {"value": 40}, scope="game", appid="42",
        vibration=vibration,
    )

    assert store.vibration_for("global") == {
        "enabled": True, "value": 100,
    }
    assert inputplumber.apply_effective(
        store, dbus, CLAW, None, vibration=vibration,
        apply_buttons=False,
    ) is True
    assert vibration.applied == {"value": 100}


def test_ip_profile_conflict_does_not_block_vibration_handoff(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.remember_profile_baseline(CLAW, "known-baseline")
    dbus._profile = "external-profile"
    store.patch_vibration("global", None, {"value": 100})
    store.patch_vibration("game", "42", {"value": 40})
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    assert inputplumber.apply_effective(
        store, dbus, CLAW, "42", vibration=vibration,
        apply_buttons=True, merge=_MERGE,
    ) is False
    assert vibration.applied == {"value": 40}


def test_ip_external_restore_uses_immutable_vibration_baseline(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.remember_vibration_baseline(
        f"inputplumber:{CLAW}",
        {"enabled": True, "value": 100},
    )
    store.patch_vibration(
        "global", None, {"enabled": False, "value": 35}
    )
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    assert inputplumber.restore_external(
        store, dbus, CLAW, vibration=vibration
    ) is True
    assert dbus.ff_enabled is True
    assert vibration.applied == {"value": 100}


def test_ip_external_restore_uses_exact_native_asus_baseline(tmp_path):
    class NativeVibration(FakeVibration):
        def __init__(self):
            super().__init__({
                "mode": "dual", "persistent": True,
                "left": 0, "right": 100,
                "min": 0, "max": 100, "step": 5, "readback": True,
            })
            self.restored = None

        def capture_baseline(self):
            return {"native_left": 1, "native_right": 63}

        def restore_baseline(self, baseline):
            self.restored = dict(baseline)
            return True

    store, dbus = _store(tmp_path), FakeDbus()
    vibration = NativeVibration()

    inputplumber.set_vibration(
        store, dbus, "rog_ally", {"left": 35, "right": 45},
        vibration=vibration,
    )
    assert store.vibration_baseline("inputplumber:rog_ally") == {
        "enabled": True,
        "left": 0,
        "right": 100,
        "native_left": 1,
        "native_right": 63,
    }
    assert store.vibration_for("global") == {
        "enabled": True,
        "left": 35,
        "right": 45,
    }
    assert inputplumber.restore_external(
        store, dbus, "rog_ally", vibration=vibration
    ) is True
    assert vibration.restored == {
        "enabled": True,
        "left": 0,
        "right": 100,
        "native_left": 1,
        "native_right": 63,
    }


def test_ip_upgrade_does_not_infer_native_baseline_from_plugin_state(tmp_path):
    class MigratedVibration(FakeVibration):
        def capture_baseline(self):
            return {"native_left": 22, "native_right": 29}

        def restore_baseline(self, baseline):
            raise AssertionError("legacy baseline must use percentage fallback")

    store, dbus = _store(tmp_path), FakeDbus()
    store.remember_vibration_baseline(
        "inputplumber:rog_ally",
        {"enabled": True, "left": 20, "right": 80},
    )
    store.patch_vibration(
        "global", None, {"enabled": True, "left": 35, "right": 45}
    )
    vibration = MigratedVibration({
        "mode": "dual", "persistent": True,
        "left": 35, "right": 45,
        "min": 0, "max": 100, "step": 5, "readback": True,
    })

    assert inputplumber.apply_effective(
        store, dbus, "rog_ally", None, vibration=vibration,
        apply_buttons=False,
    ) is True
    assert store.vibration_baseline("inputplumber:rog_ally") == {
        "enabled": True,
        "left": 20,
        "right": 80,
    }
    assert inputplumber.restore_external(
        store, dbus, "rog_ally", vibration=vibration
    ) is True
    assert vibration.applied == {"left": 20, "right": 80}


def test_ip_startup_captures_owner_baseline_before_reapply(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.patch_vibration("global", None, {"value": 40})
    vibration = FakeVibration({
        "mode": "gain", "persistent": True, "value": None,
        "min": 0, "max": 100, "step": 5, "readback": False,
    })

    assert inputplumber.apply_effective(
        store, dbus, CLAW, None, vibration=vibration,
        apply_buttons=False,
    ) is True
    assert store.vibration_baseline(f"inputplumber:{CLAW}") == {
        "enabled": True, "value": 100,
    }
    assert inputplumber.restore_external(
        store, dbus, CLAW, vibration=vibration
    ) is True
    assert vibration.applied == {"value": 100}


def test_ip_set_button_stores_and_applies(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    cfg = inputplumber.set_button(store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
                                  merge=_MERGE)
    assert store.overrides_for("global")["LeftPaddle1"] == [{"gamepad": "South"}]
    assert dbus.reset_called is False
    assert dbus.loaded == "merged-yaml"  # the merged profile was loaded
    by_src = {b["source"]: b["target"] for b in cfg["buttons"]}
    assert by_src["LeftPaddle1"] == [{"gamepad": "South"}]


def test_ip_set_button_stores_and_applies_keyboard_chord(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    chord = [{"key": "KeyLeftCtrl"}, {"key": "KeyTab"}]

    cfg = inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1", chord, merge=_MERGE,
    )

    assert store.overrides_for("global")["LeftPaddle1"] == chord
    assert dbus.loaded == "merged-yaml"
    by_source = {button["source"]: button["target"] for button in cfg["buttons"]}
    assert by_source["LeftPaddle1"] == chord


def test_ip_rejects_mixed_chord_without_profile_or_store_write(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()

    inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1",
        [{"gamepad": "South"}, {"key": "KeyTab"}], merge=_MERGE,
    )

    assert store.overrides_for("global") == {}
    assert dbus.loaded is None


def test_ip_rejects_reserved_sources_even_when_advertised(tmp_path):
    store = _store(tmp_path)
    dbus = FakeDbus(caps=[
        "Gamepad:Button:LeftPaddle1",
        "Gamepad:Button:Guide",
        "Gamepad:Button:QuickAccess",
    ])

    for source in ("Guide", "QuickAccess"):
        inputplumber.set_button(
            store, dbus, CLAW, source,
            [{"key": "KeyLeftCtrl"}, {"key": "KeyTab"}], merge=_MERGE,
        )

    assert store.overrides_for("global") == {}
    assert dbus.loaded is None


def test_ip_set_button_accepts_profile_proven_ally_paddle(
    tmp_path, monkeypatch
):
    store = _store(tmp_path)
    dbus = FakeDbus(caps=["Gamepad:Button:South"])
    monkeypatch.setattr(
        inputplumber.ip_profile,
        "proven_mapped_capabilities",
        lambda *args, **kwargs: {"LeftPaddle1", "RightPaddle1"},
    )

    config = inputplumber.set_button(
        store, dbus, "rog_ally", "LeftPaddle1",
        [{"gamepad": "South"}], merge=_MERGE,
    )

    assert config["last_apply"] is True
    assert store.overrides_for("global")["LeftPaddle1"] == [
        {"gamepad": "South"}
    ]


def test_live_buttons_does_not_probe_sources_for_non_ally():
    dbus = FakeDbus(caps=["Gamepad:Button:LeftPaddle1"])
    calls = []

    def source_paths():
        calls.append(True)
        return ["/dev/input/event2"]

    dbus.source_device_paths = source_paths

    assert inputplumber.live_buttons(
        dbus, CLAW, dbus.capabilities()
    ) == [("LeftPaddle1", "M2")]
    assert calls == []


def test_ip_set_failure_does_not_return_stale_buttons(tmp_path):
    store = _store(tmp_path)
    dbus = InvalidatingDbus()

    cfg = inputplumber.set_button(
        store,
        dbus,
        CLAW,
        "LeftPaddle1",
        [{"gamepad": "South"}],
        merge=_MERGE,
    )

    assert dbus.capability_reads == 2
    assert cfg["buttons"] == []
    assert store.overrides_for("global") == {}


def test_ip_set_button_empty_reverts_to_default(tmp_path):
    store = _store(tmp_path, {"LeftPaddle1": [{"gamepad": "South"}]})
    inputplumber.set_button(store, FakeDbus(), CLAW, "LeftPaddle1", [], merge=_MERGE)
    assert "LeftPaddle1" not in store.overrides_for("global")  # cleared → device default


def test_ip_set_button_ignores_source_not_on_this_device(tmp_path):
    # RightPaddle2 is a real Legion cap but the Claw has no such physical button.
    store, dbus = _store(tmp_path), FakeDbus()
    inputplumber.set_button(store, dbus, CLAW, "RightPaddle2", [{"gamepad": "South"}], merge=_MERGE)
    assert store.overrides_for("global") == {}
    assert dbus.loaded is None


def test_ip_reset_clears_and_loads_default(tmp_path):
    store = _store(tmp_path, {"LeftPaddle1": [{"gamepad": "South"}]})
    dbus = FakeDbus()
    inputplumber.reset(store, dbus, CLAW, merge=_MERGE)
    assert store.overrides_for("global") == {}
    assert dbus.reset_called is False
    assert dbus.loaded is None


def test_ip_identical_managed_profile_does_not_recreate_targets(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    store.remember_profile_baseline(CLAW, dbus._profile)

    assert inputplumber._apply_overrides(
        store, dbus, CLAW, {}, merge=lambda baseline, _overrides: baseline
    ) is True
    assert dbus.loaded is None
    assert store.profile_state(CLAW) is None


def test_ip_per_game_scope_is_independent_from_global(tmp_path):
    # A game remap doesn't touch global, activates its own profile, and shows in its scope.
    store, dbus = _store(tmp_path, {"RightPaddle1": [{"gamepad": "North"}]}), FakeDbus()
    inputplumber.set_button(store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
                            scope="game", appid="1234", merge=_MERGE)
    assert store.overrides_for("game", "1234")["LeftPaddle1"] == [{"gamepad": "South"}]
    assert "LeftPaddle1" not in store.overrides_for("global")   # global untouched
    assert store.overrides_for("global")["RightPaddle1"] == [{"gamepad": "North"}]
    # Editing a game value activated its own profile, and get_config (effective) now
    # shows THAT game's remap — not the global one — for the running game.
    cfg = inputplumber.get_config(store, dbus, CLAW, appid="1234")
    assert cfg["follows_global"] is False and cfg["has_game_profile"] is True
    by_src = {b["source"]: b["target"] for b in cfg["buttons"]}
    assert by_src["LeftPaddle1"] == [{"gamepad": "South"}]  # game's own value, effective


def test_ip_apply_effective_uses_global_when_following(tmp_path):
    store, dbus = _store(tmp_path, {"LeftPaddle1": [{"gamepad": "South"}]}), FakeDbus()
    # A game with no own profile follows global → applies the global overrides.
    assert inputplumber.apply_effective(
        store, dbus, CLAW, "999", merge=_MERGE
    ) is True
    assert dbus.loaded == "merged-yaml"


def test_ip_refuses_to_clobber_profile_changed_by_another_editor(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
        merge=_MERGE,
    )
    dbus._profile = "externally-edited-yaml"
    dbus.loaded = None

    cfg = inputplumber.set_button(
        store, dbus, CLAW, "RightPaddle1", [{"gamepad": "North"}],
        merge=_MERGE,
    )

    assert dbus.loaded is None
    assert "RightPaddle1" not in store.overrides_for("global")
    assert cfg["last_apply"] is False
    assert cfg["apply_error"] == "profile_conflict"


def test_ip_rejects_successful_load_without_matching_readback(tmp_path):
    store, dbus = _store(tmp_path), IgnoringProfileLoadDbus()

    inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
        merge=_MERGE,
    )

    assert store.overrides_for("global") == {}
    assert store.profile_state(CLAW) is None


def test_ip_reapplies_after_daemon_restart_restores_known_baseline(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    baseline = dbus._profile
    inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
        merge=_MERGE,
    )
    dbus._profile = baseline
    dbus.loaded = None

    inputplumber.set_button(
        store, dbus, CLAW, "RightPaddle1", [{"gamepad": "North"}],
        merge=_MERGE,
    )

    assert dbus.loaded == "merged-yaml"
    assert "RightPaddle1" in store.overrides_for("global")


def test_vibration_test_requires_stop_confirmation():
    class FailedStop:
        def test(self, pattern, channel, strength):
            assert (pattern, channel, strength) == ("pulse", "both", 50)
            return {
                "sent": True, "stopped": False, "restored": True,
                "reason": "stop_failed",
            }

    assert inputplumber.test_vibration(
        FailedStop(), "pulse", "both", 50
    )["reason"] == "stop_failed"


def test_ip_keeps_recovery_ownership_when_rollback_is_unconfirmed(tmp_path):
    store, dbus = _store(tmp_path), UnrecoverableProfileLoadDbus()
    baseline = dbus._profile

    cfg = inputplumber.set_button(
        store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
        merge=_MERGE,
    )

    state = store.profile_state(CLAW)
    assert cfg["last_apply"] is False
    assert state["baseline_yaml"] == baseline
    assert state["recovery_yamls"] == [baseline, "merged-yaml"]


# ---- HHD config ------------------------------------------------------------

def _hhd_state(mode="uinput", paddles="noob"):
    cm = {"mode": mode, mode: {"paddles_as": paddles}}
    return {"controllers": {"rog_ally": {"controller_mode": cm}}}


def _hhd_settings(*modes, version="test"):
    mode_nodes = {}
    for mode in modes:
        node = {"type": "container", "children": {}}
        if mode in {"uinput", "dualsense"}:
            node["children"]["paddles_as"] = {
                "type": "multiple",
                "options": {
                    "steam_input": "Steam Input",
                    "disabled": "Disabled",
                },
            }
        mode_nodes[mode] = node
    settings = {
        "controllers": {
            "rog_ally": {
                "type": "container",
                "children": {
                    "controller_mode": {
                        "type": "mode",
                        "modes": mode_nodes,
                    }
                },
            }
        }
    }
    if version is not None:
        settings["version"] = version
    return settings


def test_hhd_device_key_from_state():
    assert hhd_config.device_key(_hhd_state()) == "rog_ally"
    assert hhd_config.device_key({}) is None
    assert hhd_config.device_key(None) is None


def test_hhd_get_config_reads_mode_and_paddles():
    cfg = hhd_config.get_config(_hhd_state(mode="uinput", paddles="steam_input"))
    assert cfg["kind"] == "settings"
    assert cfg["mode"] == "uinput"
    assert cfg["paddles_as"] == "steam_input"
    assert cfg["mode_options"][0] == "uinput"


def test_hhd_get_config_hides_paddles_for_non_paddle_mode():
    cfg = hhd_config.get_config(_hhd_state(mode="hori_steam"))
    assert cfg["paddles_as"] is None


def test_hhd_get_config_none_without_controllers():
    assert hhd_config.get_config({})["kind"] == "none"


def test_hhd_capabilities_use_only_options_present_in_live_state():
    state = {
        "version": "test",
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                    "dualsense": {"paddles_as": "disabled"},
                    "invented_mode": {"paddles_as": "invented"},
                },
                "limits": {
                    "mode": "manual",
                    "manual": {"vibration": 40},
                },
            }
        }
    }

    capabilities = hhd_config.capabilities_report(
        state,
        "rog_ally",
        _hhd_settings("uinput", "xbox_elite", "dualsense", "disabled"),
    )

    assert capabilities["surfaces"]["settings"] == {
        "owner": "hhd",
        "availability": "supported",
        "fields": {
            "mode": "uinput",
            "mode_options": [
                "uinput", "xbox_elite", "dualsense", "disabled",
            ],
            "paddles_as": "steam_input",
            "paddles_options": ["steam_input", "disabled"],
        },
        "scope": ["global"],
        "apply": "recreate",
        "readback": "accepted",
        "evidence": "upstream",
    }
    assert capabilities["surfaces"]["vibration"] == {
        "owner": "hhd",
        "availability": "supported",
        "fields": {
            "mode": "gain",
            "persistent": True,
            "value": 40,
            "min": 0,
            "max": 100,
            "step": 20,
        },
        "scope": ["global", "game"],
        "apply": "hot",
        "readback": "accepted",
        "evidence": "upstream",
    }


def test_hhd_capabilities_omit_absent_or_ambiguous_routes():
    state = {
        "controllers": {
            "rog_ally": {
                "controller_mode": {"mode": "invented_mode"},
                "limits": {"mode": "default"},
            }
        }
    }

    assert hhd_config.capabilities_report(
        state, "rog_ally", _hhd_settings("uinput", "dualsense")
    )["surfaces"] == {}


def test_hhd_capabilities_reject_stale_settings_schema():
    state = {
        "version": "new",
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                }
            }
        },
    }

    capabilities = hhd_config.capabilities_report(
        state,
        "rog_ally",
        _hhd_settings("uinput", version="old"),
    )

    assert capabilities["surfaces"] == {}


def test_hhd_capabilities_require_versions_on_state_and_schema():
    controller = {
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                }
            }
        }
    }

    without_state_version = hhd_config.capabilities_report(
        controller,
        "rog_ally",
        _hhd_settings("uinput", version="test"),
    )
    without_schema_version = hhd_config.capabilities_report(
        {"version": "test", **controller},
        "rog_ally",
        _hhd_settings("uinput", version=None),
    )

    assert without_state_version["surfaces"] == {}
    assert without_schema_version["surfaces"] == {}


def test_hhd_build_payload_paths():
    assert hhd_config.build_payload("rog_ally", "uinput", "mode", "dualsense") == {
        "controllers": {"rog_ally": {"controller_mode": {"mode": "dualsense"}}}
    }
    assert hhd_config.build_payload("rog_ally", "uinput", "paddles_as", "steam_input") == {
        "controllers": {"rog_ally": {"controller_mode": {"uinput": {"paddles_as": "steam_input"}}}}
    }
    assert hhd_config.build_payload("rog_ally", "uinput", "bogus", "x") == {}
