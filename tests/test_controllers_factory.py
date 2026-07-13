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
    # HHD-only op is a no-op on the IP backend (returns current remap config).
    assert b.set_setting("mode", "x")["kind"] == "remap"


def test_select_hhd_backend_is_hhd():
    b = factory.select_controller_backend(
        {"manager": detect.HHD, "version": "3.19.23"}, FakeStore(), FakeDbus(), _device("rog_ally")
    )
    assert b.manager == detect.HHD
    # IP-only op is a no-op on the HHD backend.
    assert isinstance(b.set_button("LeftPaddle1", []), dict)
