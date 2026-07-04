from controllers import hhd_config, inputplumber


class FakeStore:
    def __init__(self, data=None):
        self._d = dict(data or {})

    def all(self):
        return dict(self._d)

    def set(self, s, t):
        self._d[s] = t

    def clear(self, s):
        self._d.pop(s, None)

    def replace(self, data):
        self._d = dict(data)

    def reset(self):
        self._d = {}


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

    def capabilities(self):
        return list(self._caps)

    def get_profile_yaml(self):
        return self._profile

    def load_profile_yaml(self, yaml):
        self.loaded = yaml
        return True

    def reset_default(self):
        self.reset_called = True
        return True


# ---- InputPlumber backend --------------------------------------------------

CLAW = "msi_claw_8_ai_plus"  # caps LeftPaddle1/RightPaddle1 → silkscreen M2/M1


def test_ip_get_config_lists_device_buttons_with_silkscreen_labels():
    cfg = inputplumber.get_config(FakeStore(), FakeDbus(), CLAW)
    assert cfg["kind"] == "remap"
    assert cfg["device_known"] is True
    # Per-device table order; the Claw's two grips carry real silkscreen labels.
    assert [(b["source"], b["label"]) for b in cfg["buttons"]] == [
        ("RightPaddle1", "M1"), ("LeftPaddle1", "M2"),
    ]
    # Untouched buttons have no override yet.
    assert all(b["target"] is None for b in cfg["buttons"])
    assert "South" in cfg["gamepad_targets"] and "KeyEsc" in cfg["key_targets"]


def test_ip_get_config_unknown_device_has_no_buttons_but_stays_honest():
    cfg = inputplumber.get_config(FakeStore(), FakeDbus(), "legion_go_s")
    assert cfg["kind"] == "remap"
    assert cfg["device_known"] is False
    assert cfg["buttons"] == []


def test_ip_set_button_stores_and_applies():
    store, dbus = FakeStore(), FakeDbus()
    # Inject a fake merge (the real one shells out to the system python for YAML).
    fake_merge = lambda baseline, overrides: "merged-yaml"  # noqa: E731
    cfg = inputplumber.set_button(store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
                                  merge=fake_merge)
    assert store.all()["LeftPaddle1"] == [{"gamepad": "South"}]
    assert dbus.reset_called is True   # rebuilt from the pristine default
    assert dbus.loaded == "merged-yaml"  # the merged profile was loaded
    by_src = {b["source"]: b["target"] for b in cfg["buttons"]}
    assert by_src["LeftPaddle1"] == [{"gamepad": "South"}]


def test_ip_set_button_empty_reverts_to_default():
    store = FakeStore({"LeftPaddle1": [{"gamepad": "South"}]})
    inputplumber.set_button(store, FakeDbus(), CLAW, "LeftPaddle1", [{"key": "bad"}])
    assert "LeftPaddle1" not in store.all()  # cleared → device default


def test_ip_set_button_ignores_source_not_on_this_device():
    # RightPaddle2 is a real Legion cap but the Claw has no such physical button.
    store, dbus = FakeStore(), FakeDbus()
    inputplumber.set_button(store, dbus, CLAW, "RightPaddle2", [{"gamepad": "South"}])
    assert store.all() == {}
    assert dbus.loaded is None


def test_ip_reset_clears_and_loads_default():
    store = FakeStore({"LeftPaddle1": [{"gamepad": "South"}]})
    dbus = FakeDbus()
    inputplumber.reset(store, dbus)
    assert store.all() == {}
    assert dbus.reset_called is True


# ---- HHD config ------------------------------------------------------------

def _hhd_state(mode="uinput", paddles="noob"):
    cm = {"mode": mode, mode: {"paddles_as": paddles}}
    return {"controllers": {"rog_ally": {"controller_mode": cm}}}


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


def test_hhd_build_payload_paths():
    assert hhd_config.build_payload("rog_ally", "uinput", "mode", "dualsense") == {
        "controllers": {"rog_ally": {"controller_mode": {"mode": "dualsense"}}}
    }
    assert hhd_config.build_payload("rog_ally", "uinput", "paddles_as", "steam_input") == {
        "controllers": {"rog_ally": {"controller_mode": {"uinput": {"paddles_as": "steam_input"}}}}
    }
    assert hhd_config.build_payload("rog_ally", "uinput", "bogus", "x") == {}
