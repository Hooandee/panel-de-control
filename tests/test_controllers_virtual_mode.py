from controllers.store import RemapStore
from controllers.virtual_mode import HhdVirtualModeAdapter


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
