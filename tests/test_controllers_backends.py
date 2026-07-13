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


_MERGE = lambda baseline, overrides: "merged-yaml"  # noqa: E731 — the real one shells to system python


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
    cfg = inputplumber.get_config(_store(tmp_path), FakeDbus(), "legion_go_s")
    assert cfg["kind"] == "remap"
    assert cfg["device_known"] is False
    assert cfg["buttons"] == []


def test_ip_set_button_stores_and_applies(tmp_path):
    store, dbus = _store(tmp_path), FakeDbus()
    cfg = inputplumber.set_button(store, dbus, CLAW, "LeftPaddle1", [{"gamepad": "South"}],
                                  merge=_MERGE)
    assert store.overrides_for("global")["LeftPaddle1"] == [{"gamepad": "South"}]
    assert dbus.reset_called is True   # rebuilt from the pristine default
    assert dbus.loaded == "merged-yaml"  # the merged profile was loaded
    by_src = {b["source"]: b["target"] for b in cfg["buttons"]}
    assert by_src["LeftPaddle1"] == [{"gamepad": "South"}]


def test_ip_set_button_empty_reverts_to_default(tmp_path):
    store = _store(tmp_path, {"LeftPaddle1": [{"gamepad": "South"}]})
    inputplumber.set_button(store, FakeDbus(), CLAW, "LeftPaddle1", [{"key": "bad"}], merge=_MERGE)
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
    inputplumber.reset(store, dbus)
    assert store.overrides_for("global") == {}
    assert dbus.reset_called is True


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
    assert inputplumber.apply_effective(store, dbus, "999", merge=_MERGE) is True
    assert dbus.loaded == "merged-yaml"


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
