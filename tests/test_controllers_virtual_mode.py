from controllers.store import RemapStore
from controllers.virtual_mode import (
    HhdVirtualModeAdapter,
    InputPlumberVirtualModeAdapter,
)


def _settings(*modes):
    return {
        "version": "4.1.8",
        "controllers": {
            "rog_ally": {
                "children": {
                    "controller_mode": {
                        "type": "mode",
                        "modes": {
                            mode: {
                                "type": "container",
                                "children": {
                                    "paddles_as": {
                                        "type": "multiple",
                                        "options": {
                                            "steam_input": "Steam Input",
                                            "disabled": "Disabled",
                                        },
                                    },
                                },
                            }
                            for mode in modes
                        },
                    },
                },
            },
        },
    }


def _state(mode="uinput", paddles="steam_input"):
    return {
        "version": "4.1.8",
        "controllers": {
            "rog_ally": {
                "controller_mode": {
                    "mode": mode,
                    mode: {"paddles_as": paddles},
                },
            },
        },
    }


class HhdApi:
    def __init__(self, state, settings):
        self.state = state
        self.settings = settings
        self.posts = []
        self.ignore = False

    def read_state(self):
        return self.state

    def read_settings(self):
        return self.settings

    def post_state(self, payload):
        self.posts.append(payload)
        if self.ignore:
            return self.state
        node = payload["controllers"]["rog_ally"]["controller_mode"]
        current = self.state["controllers"]["rog_ally"]["controller_mode"]
        if "mode" in node:
            current["mode"] = node["mode"]
        for mode, subtree in node.items():
            if mode != "mode" and isinstance(subtree, dict):
                current.setdefault(mode, {}).update(subtree)
        return self.state


def _adapter(tmp_path, api, sys_root=None):
    return HhdVirtualModeAdapter(
        RemapStore(str(tmp_path / "controllers.json")),
        "rog_ally",
        api.read_state,
        api.read_settings,
        api.post_state,
        sys_root=str(sys_root or tmp_path / "sys/class/input"),
        sleep=lambda _: None,
    )


def test_hhd_filters_hidden_and_unknown_live_modes(tmp_path):
    api = HhdApi(
        _state(),
        _settings("uinput", "dualsense", "hidden", "disabled", "made_up"),
    )

    assert _adapter(tmp_path, api).capabilities() == {
        "current": "uinput",
        "options": ["auto", "uinput", "dualsense"],
        "scope": ["global", "game"],
        "readiness": "evdev_identity",
    }


def test_auto_uses_immutable_external_baseline(tmp_path):
    api = HhdApi(_state("uinput"), _settings("uinput", "dualsense"))
    adapter = _adapter(tmp_path, api)

    assert adapter.apply("dualsense")["config_confirmed"] is True
    assert adapter.apply("auto")["actual"] == {
        "mode": "uinput", "paddles_as": "steam_input",
    }
    assert api.state["controllers"]["rog_ally"]["controller_mode"]["mode"] == (
        "uinput"
    )


def test_hhd_ownership_survives_adapter_restart(tmp_path):
    api = HhdApi(_state("uinput"), _settings("uinput", "dualsense"))

    assert _adapter(tmp_path, api).apply("dualsense")["config_confirmed"] is True

    restarted = _adapter(tmp_path, api)
    result = restarted.apply("auto")

    assert result["config_confirmed"] is True
    assert result["actual"] == {
        "mode": "uinput", "paddles_as": "steam_input",
    }


def test_rejected_hhd_echo_rolls_back_to_previous_mode(tmp_path):
    api = HhdApi(_state("uinput"), _settings("uinput", "dualsense"))
    adapter = _adapter(tmp_path, api)
    api.ignore = True

    result = adapter.apply("dualsense")

    assert result == {
        "config_confirmed": False,
        "rollback_confirmed": True,
        "actual": {"mode": "uinput", "paddles_as": "steam_input"},
        "reason": "config_echo_mismatch",
    }


def _input_node(root, event, vendor, product, name):
    base = root / event / "device"
    (base / "id").mkdir(parents=True)
    (base / "id/vendor").write_text(vendor)
    (base / "id/product").write_text(product)
    (base / "name").write_text(name)


def test_wait_ready_requires_one_exact_hhd_virtual_gamepad(tmp_path):
    root = tmp_path / "sys/class/input"
    _input_node(root, "event4", "045e", "02e3", "Xbox Elite")
    api = HhdApi(_state("xbox_elite"), _settings("xbox_elite"))
    adapter = _adapter(tmp_path, api, root)

    assert adapter.wait_ready("xbox_elite", timeout=0) is True

    _input_node(root, "event5", "045e", "02e3", "Xbox Elite")
    assert adapter.wait_ready("xbox_elite", timeout=0) is False


def test_readiness_failure_can_restore_the_exact_previous_profile(tmp_path):
    api = HhdApi(_state("uinput"), _settings("uinput", "dualsense"))
    adapter = _adapter(tmp_path, api)

    assert adapter.apply("dualsense")["config_confirmed"] is True
    assert adapter.wait_ready("dualsense", timeout=0) is False
    assert adapter.rollback_last() is True
    assert api.state["controllers"]["rog_ally"]["controller_mode"]["mode"] == (
        "uinput"
    )


def test_hhd_does_not_overwrite_a_foreign_live_profile(tmp_path):
    api = HhdApi(
        _state("uinput"),
        _settings("uinput", "dualsense", "xbox_elite"),
    )
    adapter = _adapter(tmp_path, api)

    assert adapter.apply("dualsense")["config_confirmed"] is True
    api.state = _state("xbox_elite", "disabled")
    posts = len(api.posts)

    result = adapter.apply("uinput")

    assert result["reason"] == "profile_conflict"
    assert result["actual"] == {
        "mode": "xbox_elite", "paddles_as": "disabled",
    }
    assert len(api.posts) == posts


class InputPlumberApi:
    def __init__(self, reads, supported=None):
        self.reads = iter(reads)
        self.supported = supported or [
            "xb360", "xbox-elite", "ds5-edge", "keyboard", "mouse",
        ]
        self.writes = []

    def target_device_types(self):
        return next(self.reads)

    def supported_target_device_ids(self):
        return list(self.supported)

    def set_target_devices(self, targets):
        self.writes.append(list(targets))
        return True


def _ip_adapter(tmp_path, api):
    return InputPlumberVirtualModeAdapter(
        RemapStore(str(tmp_path / "controllers.json")),
        api,
        "legion_go",
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
    )


def test_inputplumber_mode_replaces_only_gamepad_and_waits_for_exact_set(
    tmp_path,
):
    baseline = ["xbox-elite", "mouse", "keyboard", "touchpad"]
    desired = ["ds5-edge", "mouse", "keyboard", "touchpad"]
    api = InputPlumberApi([baseline, baseline, desired])
    adapter = _ip_adapter(tmp_path, api)

    applied = adapter.apply("ds5-edge")
    ready = adapter.wait_ready(timeout=1)

    assert applied == {
        "accepted": True,
        "ready": False,
        "rollback_confirmed": True,
        "actual": "xbox-elite",
        "reason": None,
    }
    assert ready == {
        "ready": True,
        "rollback_confirmed": True,
        "actual": "ds5-edge",
    }
    assert api.writes == [desired]


def test_inputplumber_readiness_failure_restores_all_previous_targets(
    tmp_path,
):
    baseline = ["xbox-elite", "mouse", "keyboard", "touchpad"]
    desired = ["ds5-edge", "mouse", "keyboard", "touchpad"]
    api = InputPlumberApi([baseline, ["keyboard"], baseline])
    adapter = _ip_adapter(tmp_path, api)

    assert adapter.apply("ds5-edge")["accepted"] is True
    outcome = adapter.wait_ready(timeout=0)

    assert outcome == {
        "ready": False,
        "rollback_confirmed": True,
        "actual": None,
    }
    assert api.writes == [desired, baseline]


def test_inputplumber_auto_restores_immutable_external_baseline(tmp_path):
    baseline = ["xbox-elite", "keyboard"]
    custom = ["ds5-edge", "keyboard"]
    api = InputPlumberApi([baseline, custom, custom, baseline])
    adapter = _ip_adapter(tmp_path, api)

    assert adapter.apply("ds5-edge")["accepted"] is True
    assert adapter.wait_ready(timeout=0)["ready"] is True
    assert adapter.apply("auto")["accepted"] is True
    assert adapter.wait_ready(timeout=0)["ready"] is True
    assert api.writes == [custom, baseline]


def test_inputplumber_cancel_rolls_back_a_pending_target_transition(
    tmp_path,
):
    baseline = ["xbox-elite", "keyboard"]
    desired = ["ds5-edge", "keyboard"]
    api = InputPlumberApi([baseline, baseline])
    adapter = _ip_adapter(tmp_path, api)

    assert adapter.apply("ds5-edge")["accepted"] is True
    assert adapter.cancel() is True

    assert api.writes == [desired, baseline]
