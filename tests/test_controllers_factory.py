from types import SimpleNamespace

from controllers import detect, factory


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


def test_select_hhd_backend_is_hhd():
    b = factory.select_controller_backend(
        {"manager": detect.HHD, "version": "3.19.23"}, FakeStore(), FakeDbus(), _device("rog_ally")
    )
    assert b.manager == detect.HHD
    # IP-only op is a no-op on the HHD backend.
    assert isinstance(b.set_button("LeftPaddle1", []), dict)


def test_bazzite_43_ayaneo_prefers_hhd_magic_modules(monkeypatch, tmp_path):
    state = {
        "controllers": {"ayaneo": {"controller_mode": {"mode": "uinput", "uinput": {}}}},
        "magic_modules": {"magic_modules": {
            "pop_left": False,
            "pop_right": False,
            "pop_both": False,
            "info_left": "Cross / Joystick",
            "info_right": r"ABXY \ Joystick",
        }},
    }
    calls = []

    def read_state(root="/", timeout=5, language=None):
        calls.append((timeout, language))
        return state

    monkeypatch.setattr(factory.hhd_api, "read_state", read_state)

    backend = factory.select_controller_backend(
        {"manager": detect.HHD, "version": "4.1.12"},
        FakeStore(),
        FakeDbus(),
        _device("ayaneo_3"),
        root=str(tmp_path),
    )

    assert backend.get_config()["magic_modules"] == {
        "supported": True,
        "source": "hhd",
        "left": "connected",
        "right": "connected",
        "busy": False,
    }
    assert (0.5, "en") in calls


def test_bazzite_44_contract_without_hhd_never_exposes_direct_hid_writes(tmp_path):
    backend = factory.select_controller_backend(
        {"manager": detect.INPUTPLUMBER, "version": "0.79.0"},
        FakeStore(),
        FakeDbus(),
        _device("ayaneo_3"),
        root=str(tmp_path),
    )

    magic = backend.get_config()["magic_modules"]
    assert magic["supported"] is False
    assert magic["source"] == "hhd"
    assert backend.run_action("eject_both")["outcome"] == "unavailable"


def test_non_ayaneo_never_gets_magic_module_actions(tmp_path):
    backend = factory.select_controller_backend(
        {"manager": detect.INPUTPLUMBER, "version": "0.79.0"},
        FakeStore(),
        FakeDbus(),
        _device("zotac_gaming_zone"),
        root=str(tmp_path),
    )

    assert "magic_modules" not in backend.get_config()
    assert backend.run_action("eject_both")["outcome"] == "unavailable"


def test_magic_module_action_result_is_kept_for_sanitised_diagnostics():
    class Actions:
        def state(self):
            return {"supported": True, "source": "hhd"}

        def run(self, action):
            return {
                "action": action,
                "outcome": "unverifiable",
                "accepted": None,
                "reason": "hhd_post_unconfirmed",
            }

    backend = factory.ControllerBackend(actions=Actions())

    result = backend.run_action("eject_left")

    assert backend.diagnostics()["last_action"] == result
