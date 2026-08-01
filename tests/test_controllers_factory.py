from types import SimpleNamespace

from controllers import detect, factory
from controllers.store import RemapStore


def _device(key):
    return SimpleNamespace(key=key)


class FakeStore:
    def effective_overrides(self, appid):
        return {}

    def overrides_for(self, scope, appid=None):
        return {}

    def is_following_global(self, appid):
        return True

    def has_game(self, appid):
        return False


class FakeDbus:
    def capabilities(self):
        return ["Gamepad:Button:LeftPaddle1"]

    def diagnostics(self):
        return {
            "composite_path_available": True,
            "capability_count": 1,
            "capabilities": ["Gamepad:Button:LeftPaddle1"],
            "last_operation": None,
        }


class FakeVibration:
    def __init__(self):
        self.applied = None

    def state(self):
        return {
            "mode": "dual", "persistent": True, "left": 90, "right": 80,
            "min": 0, "max": 100, "step": 5, "readback": True,
        }

    def apply(self, patch):
        self.applied = dict(patch)
        return True


def test_select_none_backend():
    b = factory.select_controller_backend({"manager": detect.NONE, "version": None}, FakeStore(), FakeDbus(), _device("legion_go_2"))
    cfg = b.get_config()
    assert cfg["kind"] == "none"
    assert cfg["manager"] == detect.NONE
    assert cfg["supported"] is False
    # Writes are safe no-ops returning the same config.
    assert b.set_button("x", [])["kind"] == "none"
    assert b.set_setting("mode", "uinput")["kind"] == "none"
    assert b.reset()["kind"] == "none"


def test_no_backend_reports_no_mutable_surfaces():
    backend = factory.ControllerBackend()

    assert backend.get_capabilities() == {
        "device_key": None,
        "manager": detect.NONE,
        "surfaces": {},
    }
    assert backend.get_config()["capabilities"] == backend.get_capabilities()


def test_no_backend_integrated_diagnostics_has_stable_empty_shape():
    backend = factory.ControllerBackend()

    assert backend.get_integrated_diagnostics() == {
        "device_key": None,
        "sources": [],
        "batteries": [],
        "inputs": {},
        "motion": None,
        "vibration": None,
        "last_operations": {},
    }


def test_component_adapter_is_honest_without_an_owner():
    backend = factory.ControllerBackend()

    empty = backend.apply_component("buttons", {}, "42", 1)
    requested = backend.apply_component(
        "vibration", {"value": 40}, "42", 1
    )

    assert empty.status == "applied"
    assert empty.actual == {}
    assert requested.status == "unsupported"
    assert requested.reason == "unsupported"


def test_inputplumber_button_component_uses_exact_profile_readback(
    monkeypatch,
):
    monkeypatch.setattr(factory, "VibrationController", lambda *args: FakeVibration())
    monkeypatch.setattr(factory.ip, "_apply_overrides", lambda *args: True)
    backend = factory.IpBackend(
        FakeStore(), FakeDbus(), device_key="rog_ally"
    )
    desired = {"LeftPaddle1": [{"key": "KeyTab"}]}

    result = backend.apply_component("buttons", desired, "42", 7)

    assert result.status == "applied"
    assert result.owner == "inputplumber"
    assert result.actual == desired


def test_ip_report_composes_only_live_buttons_and_persistent_vibration(
    tmp_path, monkeypatch
):
    store = RemapStore(str(tmp_path / "controllers.json"))
    dbus = FakeDbus()
    monkeypatch.setattr(
        factory,
        "VibrationController",
        lambda *args: FakeVibration(),
    )
    backend = factory.IpBackend(
        store, dbus, device_key="rog_ally"
    )

    capabilities = backend.get_capabilities("42")

    assert capabilities["device_key"] == "rog_ally"
    assert capabilities["manager"] == detect.INPUTPLUMBER
    assert capabilities["surfaces"]["buttons"] == {
        "owner": "inputplumber",
        "availability": "supported",
        "fields": {
            "buttons": [
                {"source": "LeftPaddle1", "label": "M2"},
            ],
            "gamepad_targets": list(factory.ip_profile.GAMEPAD_TARGETS),
            "key_targets": list(factory.ip_profile.KEY_TARGETS),
        },
        "scope": ["global", "game"],
        "apply": "hot",
        "readback": "exact",
        "evidence": "upstream",
    }
    assert capabilities["surfaces"]["vibration"] == {
        "owner": "native",
        "availability": "supported",
        "fields": {
            "mode": "dual",
            "channels": ["left", "right"],
            "readback": "driver",
            "min": 0,
            "max": 100,
            "step": 5,
            "test": {
                "patterns": ["pulse"],
                "channels": ["left", "right", "both"],
            },
        },
        "scope": ["global", "game"],
        "apply": "hot",
        "readback": "exact",
        "evidence": "upstream",
    }


def test_ip_report_omits_unproven_surfaces(tmp_path, monkeypatch):
    store = RemapStore(str(tmp_path / "controllers.json"))
    dbus = FakeDbus()
    dbus.capabilities = lambda: []
    monkeypatch.setattr(
        factory,
        "VibrationController",
        lambda *args: SimpleNamespace(state=lambda: None),
    )
    backend = factory.IpBackend(
        store, dbus, device_key="rog_ally"
    )

    assert backend.get_capabilities()["surfaces"] == {}


def test_select_ip_backend_stamps_manager_and_version():
    b = factory.select_controller_backend(
        {"manager": detect.INPUTPLUMBER, "version": "0.77.4"}, FakeStore(), FakeDbus(), _device("msi_claw_8_ai_plus")
    )
    cfg = b.get_config()
    assert cfg["kind"] == "remap"
    assert cfg["manager"] == detect.INPUTPLUMBER
    assert cfg["manager_version"] == "0.77.4"
    assert cfg["supported"] is True
    # The device key drives the per-device silkscreen button table.
    assert [b["label"] for b in cfg["buttons"]] == ["M2"]  # only LeftPaddle1 is in caps
    assert b.diagnostics()["mapped_buttons"] == [
        {"source": "LeftPaddle1", "label": "M2"},
    ]
    # HHD-only op is a no-op on the IP backend (returns current remap config).
    assert b.set_setting("mode", "x")["kind"] == "remap"


def test_ip_config_is_backward_compatible_except_capabilities(
    tmp_path, monkeypatch
):
    store = RemapStore(str(tmp_path / "controllers.json"))
    monkeypatch.setattr(
        factory, "VibrationController",
        lambda *args: SimpleNamespace(state=lambda: None),
    )
    backend = factory.IpBackend(
        store, FakeDbus(), version="0.77.4",
        device_key="msi_claw_8_ai_plus",
    )

    config = backend.get_config()
    legacy = {
        key: value for key, value in config.items()
        if key != "capabilities"
    }

    assert legacy == {
        "kind": "remap",
        "device_known": True,
        "buttons": [
            {"source": "LeftPaddle1", "label": "M2", "target": None},
        ],
        "gamepad_targets": list(factory.ip_profile.GAMEPAD_TARGETS),
        "key_targets": list(factory.ip_profile.KEY_TARGETS),
        "follows_global": True,
        "has_game_profile": False,
            "vibration": {
                "supported": False,
                "enabled": None,
                "test_supported": False,
                "test_patterns": [],
                "test_channels": [],
            },
        "manager": detect.INPUTPLUMBER,
        "manager_version": "0.77.4",
        "supported": True,
    }


def test_ip_backend_reports_persisted_profile_ownership(tmp_path):
    store = RemapStore(str(tmp_path / "controllers.json"))
    store.remember_profile_baseline(
        "legion_go", "version: 1\nkind: DeviceProfile\n"
    )
    backend = factory.IpBackend(
        store, FakeDbus(), device_key="legion_go"
    )

    assert backend.owns_loaded_profile() is True


def test_ip_backend_reports_vibration_apply_independently(
    tmp_path, monkeypatch
):
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.IpBackend(
        store, FakeDbus(), device_key="legion_go"
    )
    monkeypatch.setattr(
        factory.ip,
        "apply_effective_components",
        lambda *args, **kwargs: {
            "buttons": False,
            "vibration": True,
        },
    )

    assert backend.apply_effective("42") is False
    assert backend.get_config("42")["vibration"]["last_apply"] is True


def test_select_hhd_backend_is_hhd():
    b = factory.select_controller_backend(
        {"manager": detect.HHD, "version": "3.19.23"}, FakeStore(), FakeDbus(), _device("rog_ally")
    )
    assert b.manager == detect.HHD
    # IP-only op is a no-op on the HHD backend.
    assert isinstance(b.set_button("LeftPaddle1", []), dict)


def test_hhd_config_and_capabilities_share_one_live_state(
    tmp_path, monkeypatch
):
    state = {
        "version": "test",
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                }
            }
        }
    }
    reads = []

    def read_state():
        reads.append(True)
        return state

    settings = {
        "version": "test",
        "controllers": {
            "rog_ally": {
                "type": "container",
                "children": {
                    "controller_mode": {
                        "type": "mode",
                        "modes": {
                            "uinput": {
                                "type": "container",
                                "children": {
                                    "paddles_as": {
                                        "type": "multiple",
                                        "options": {
                                            "steam_input": "Steam Input",
                                        },
                                    }
                                },
                            }
                        },
                    }
                },
            }
        }
    }
    monkeypatch.setattr(factory.hhd_api, "read_state", read_state)
    monkeypatch.setattr(
        factory.hhd_api, "read_settings", lambda: settings
    )
    backend = factory.HhdBackend(
        store=RemapStore(str(tmp_path / "controllers.json")),
        device_key="rog_ally",
    )

    config = backend.get_config()

    assert reads == [True]
    assert config["mode"] == "uinput"
    assert config["capabilities"]["surfaces"]["settings"]["fields"][
        "mode"
    ] == "uinput"


def test_hhd_config_is_backward_compatible_except_capabilities(
    tmp_path, monkeypatch
):
    state = {
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                }
            }
        }
    }
    monkeypatch.setattr(factory.hhd_api, "read_state", lambda: state)
    monkeypatch.setattr(factory.hhd_api, "read_settings", lambda: None)
    backend = factory.HhdBackend(
        version="3.19.23",
        store=RemapStore(str(tmp_path / "controllers.json")),
        device_key="rog_ally",
    )

    config = backend.get_config()
    legacy = {
        key: value for key, value in config.items()
        if key != "capabilities"
    }

    assert legacy == {
        "kind": "settings",
        "device_key": "rog_ally",
        "mode": "uinput",
        "mode_options": list(factory.hhd_config.MODES),
        "paddles_as": "steam_input",
        "paddles_options": list(factory.hhd_config.PADDLES_AS),
        "virtual_controller": {
            "supported": False,
            "mode": "auto",
            "actual_mode": "uinput",
            "options": [],
            "scope": [],
        },
        "vibration": {
            "supported": False,
            "enabled": None,
            "test_supported": False,
        },
        "follows_global": True,
        "has_game_profile": False,
        "manager": detect.HHD,
        "manager_version": "3.19.23",
        "supported": True,
    }


def test_hhd_virtual_mode_is_persisted_per_game_and_readiness_confirmed(
    tmp_path, monkeypatch
):
    state = {
        "version": "test",
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": "uinput",
                    "uinput": {"paddles_as": "steam_input"},
                    "dualsense": {"paddles_as": "steam_input"},
                },
            },
        },
    }
    settings = {
        "version": "test",
        "controllers": {
            "rog_ally": {
                "children": {
                    "controller_mode": {
                        "type": "mode",
                        "modes": {
                            "uinput": {"children": {}},
                            "dualsense": {"children": {}},
                            "hidden": {"children": {}},
                        },
                    },
                },
            },
        },
    }
    posts = []

    def post(payload):
        posts.append(payload)
        node = payload["controllers"]["rog_ally"]["controller_mode"]
        current = state["controllers"]["rog_ally"]["controller_mode"]
        if "mode" in node:
            current["mode"] = node["mode"]
        return state

    monkeypatch.setattr(factory.hhd_api, "read_state", lambda: state)
    monkeypatch.setattr(factory.hhd_api, "read_settings", lambda: settings)
    monkeypatch.setattr(factory.hhd_api, "post_state", post)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "4.1.8", store, FakeDbus(), "rog_ally"
    )
    backend._virtual_mode.wait_ready = lambda mode: mode == "dualsense"

    config = backend.set_virtual_mode(
        "dualsense", "game", "42"
    )
    desired = store.effective_virtual_controller("42")
    applied = backend.apply_component(
        "virtual_controller", desired, "42", 8
    )
    ready = backend.wait_ready("42", 8)

    assert config["virtual_controller"]["mode"] == "dualsense"
    assert applied.status == "accepted_unverifiable"
    assert ready.status == "applied"
    assert posts[0] == {
        "controllers": {
            "rog_ally": {
                "controller_mode": {"mode": "dualsense"},
            },
        },
    }
    assert store.virtual_mode_baseline("hhd:rog_ally") == {
        "mode": "uinput", "paddles_as": "steam_input",
    }


def _hhd_ally_owner(monkeypatch, value=80):
    state = {
        "controllers": {
            "rog_ally": {
                "controller_mode": {"mode": "uinput"},
                "limits": {
                    "mode": "manual",
                    "manual": {"vibration": value},
                },
            }
        }
    }
    posts = []

    def post(payload):
        posts.append(payload)
        limits = (
            payload.get("controllers", {})
            .get("rog_ally", {})
            .get("limits")
        )
        if limits:
            current = state["controllers"]["rog_ally"]["limits"]
            if "mode" in limits:
                current["mode"] = limits["mode"]
            if "manual" in limits:
                current.setdefault("manual", {}).update(limits["manual"])
        return state

    monkeypatch.setattr(factory.hhd_api, "read_state", lambda: state)
    monkeypatch.setattr(factory.hhd_api, "post_state", post)
    return state, posts


def test_hhd_asus_vibration_is_saved_and_reapplied_per_game(
    tmp_path, monkeypatch
):
    _state, posts = _hhd_ally_owner(monkeypatch)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    cfg = backend.set_vibration(
        {"value": 40}, scope="game", appid="42"
    )

    assert cfg["vibration"]["value"] == 40
    assert cfg["follows_global"] is False
    assert posts[-1]["controllers"]["rog_ally"]["limits"] == {
        "manual": {"vibration": 40},
    }
    assert backend.apply_effective("42") is True
    assert posts[-1]["controllers"]["rog_ally"]["limits"]["manual"] == {
        "vibration": 40,
    }


def test_hhd_asus_disable_preserves_motor_levels_for_reenable(
    tmp_path, monkeypatch
):
    _state, posts = _hhd_ally_owner(monkeypatch)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    backend.set_vibration({"enabled": False}, scope="global")
    assert store.effective_vibration(None) == {
        "enabled": False, "value": 80,
    }
    assert posts[-1]["controllers"]["rog_ally"]["limits"]["manual"] == {
        "vibration": 0,
    }

    backend.set_vibration({"enabled": True}, scope="global")
    assert posts[-1]["controllers"]["rog_ally"]["limits"]["manual"] == {
        "vibration": 80,
    }


def test_hhd_game_vibration_captures_global_baseline_for_handoff(
    tmp_path, monkeypatch
):
    _state, posts = _hhd_ally_owner(monkeypatch)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    backend.set_vibration({"value": 40}, scope="game", appid="42")

    assert store.vibration_for("global") == {
        "enabled": True, "value": 80,
    }
    assert backend.apply_effective(None) is True
    assert posts[-1]["controllers"]["rog_ally"]["limits"]["manual"] == {
        "vibration": 80,
    }


def test_hhd_startup_captures_owner_baseline_before_reapply(
    tmp_path, monkeypatch
):
    _state, posts = _hhd_ally_owner(monkeypatch)
    store = RemapStore(str(tmp_path / "controllers.json"))
    store.patch_vibration("global", None, {"value": 40})
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    assert backend.apply_effective(None) is True
    assert store.vibration_baseline("hhd:rog_ally") == {
        "enabled": True, "value": 80,
    }
    assert backend.restore_external() is True
    assert posts[-1]["controllers"]["rog_ally"]["limits"]["manual"] == {
        "vibration": 80,
    }


def test_hhd_set_setting_keeps_vibration_and_scope_contract(
    tmp_path, monkeypatch
):
    _hhd_ally_owner(monkeypatch)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally",
    )

    cfg = backend.set_setting("mode", "uinput")

    assert cfg["vibration"]["supported"] is True
    assert cfg["follows_global"] is True
    assert cfg["has_game_profile"] is False


def test_hhd_vibration_is_hidden_until_limits_are_already_manual(
    tmp_path, monkeypatch
):
    state, posts = _hhd_ally_owner(monkeypatch)
    state["controllers"]["rog_ally"]["limits"]["mode"] = "default"
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    cfg = backend.set_vibration({"value": 40}, scope="global")

    assert cfg["vibration"]["supported"] is False
    assert posts == []


def test_hhd_vibration_echo_mismatch_rolls_back_config(
    tmp_path, monkeypatch
):
    state, _posts = _hhd_ally_owner(monkeypatch)
    calls = []

    def ignore_first_then_echo(payload):
        calls.append(payload)
        if len(calls) == 2:
            value = payload["controllers"]["rog_ally"]["limits"][
                "manual"
            ]["vibration"]
            state["controllers"]["rog_ally"]["limits"]["manual"][
                "vibration"
            ] = value
        return state

    monkeypatch.setattr(factory.hhd_api, "post_state", ignore_first_then_echo)
    store = RemapStore(str(tmp_path / "controllers.json"))
    backend = factory.HhdBackend(
        "3.19.23", store, FakeDbus(), "rog_ally"
    )

    cfg = backend.set_vibration({"value": 40}, scope="global")

    assert cfg["vibration"]["last_apply"] is False
    assert backend.diagnostics()["vibration"]["rollback_confirmed"] is True
    assert state["controllers"]["rog_ally"]["limits"]["manual"][
        "vibration"
    ] == 80
    assert backend.get_config()["vibration"]["last_apply"] is False


def test_unknown_inputplumber_device_cannot_write_vibration(tmp_path):
    store = RemapStore(str(tmp_path / "controllers.json"))
    dbus = FakeDbus()
    backend = factory.IpBackend(
        store, dbus, device_key="unknown_device"
    )

    cfg = backend.get_config()

    assert cfg["vibration"]["supported"] is False
    assert backend.test_vibration(
        "pulse", "both", 100
    )["reason"] == "unsupported"
