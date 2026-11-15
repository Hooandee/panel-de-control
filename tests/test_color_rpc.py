"""RPC-level tests for the Pantalla color controls.

Same Plugin bootstrap as test_cpu_rpc: fake decky + fake TDP backend so _init never
touches live hardware, plus a fake gamescope color backend so no real X display is
needed and we can assert what got applied.
"""
import asyncio
import dataclasses
import sys
import types
from main_harness import load_main


class _FakeColorBackend:
    def __init__(self, supported=True):
        self.supported = supported
        self.probe_detail = "fake"
        self.applied = []

    def apply(self, state):
        if not self.supported:
            return False
        self.applied.append(dict(state))
        return True


def _make_plugin(tmp_path, monkeypatch, color=None):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = False
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

        def level_limits(self):
            return {}

        def set_tdp(self, w, ac):
            return TdpResult(w, w, True, "")

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())

    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)

    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)

    fake_color = color if color is not None else _FakeColorBackend()
    monkeypatch.setattr(main, "GamescopeColorBackend", lambda *a, **k: fake_color)
    return main.Plugin(), fake_color


def test_set_calibration_is_global(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_calibration({"temperature": -40, "contrast": 25}))
    assert st["temperature"] == -40 and st["contrast"] == 25
    assert color.applied[-1]["contrast"] == 25
    assert st["preview"] is False  # confirmed → not pending


def test_set_calibration_advanced_fields(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_calibration(
        {"gamma": 30, "hue": -20, "gain_r": 120, "gain_g": 90, "gain_b": 110, "vibrance": 50}))
    assert st["gamma"] == 30 and st["hue"] == -20 and st["vibrance"] == 50
    assert st["gain_r"] == 120 and st["gain_g"] == 90 and st["gain_b"] == 110
    assert color.applied[-1]["gamma"] == 30  # pushed to hardware
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["gamma"] == 30  # persisted


def test_preview_calibration_applies_live_but_does_not_persist(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.preview_calibration({"temperature": -30, "contrast": 40}))
    assert st["preview"] is True  # pending confirmation
    assert st["temperature"] == -30 and st["contrast"] == 40
    assert color.applied[-1]["contrast"] == 40  # applied live to hardware
    # NOT persisted: a fresh instance sees native calibration
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["contrast"] == 0


def test_preview_calibration_honors_safety_floor(tmp_path, monkeypatch):
    # A LIVE preview must be clamped to the same safe range as a saved value, so a
    # mis-drag can't push the panel past the -60 contrast floor before confirming.
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.preview_calibration({"contrast": -100}))
    assert st["contrast"] == -60
    assert color.applied[-1]["contrast"] == -60


def test_empty_preview_payload_restores_an_existing_preview(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration({"contrast": 20}))
    asyncio.run(p.preview_calibration({"contrast": 60}))
    color.applied.clear()

    st = asyncio.run(p.preview_calibration({"saturation": 150}))

    assert st["preview"] is False and st["contrast"] == 20
    assert color.applied[-1]["contrast"] == 20


def test_confirm_after_preview_persists(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.preview_calibration({"temperature": -30, "contrast": 40}))
    asyncio.run(p.set_calibration({"temperature": -30, "contrast": 40}))
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["contrast"] == 40  # saved


def test_auto_revert_drops_preview_and_reapplies_saved(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration({"temperature": 0, "contrast": 20}))       # saved baseline
    asyncio.run(p.preview_calibration({"temperature": 0, "contrast": 60}))   # unconfirmed preview
    assert asyncio.run(p.get_color_state())["contrast"] == 60
    p._do_color_revert()                         # timer fires
    st = asyncio.run(p.get_color_state())
    assert st["preview"] is False and st["contrast"] == 20  # back to saved
    assert color.applied[-1]["contrast"] == 20


def test_preview_cannot_be_confirmed_into_a_different_scope(tmp_path, monkeypatch):
    p, _color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.preview_calibration(
        {"contrast": 40}, "game", "42", "42"
    ))

    st = asyncio.run(p.set_calibration(
        {"contrast": 40}, "global", None, "42"
    ))

    assert st["preview"] is True
    assert p._color.effective(None)["contrast"] == 0


def test_active_preview_cannot_move_to_a_different_scope(tmp_path, monkeypatch):
    p, _color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.preview_calibration(
        {"contrast": 40}, "game", "42", "42"
    ))

    st = asyncio.run(p.preview_calibration(
        {"contrast": -20}, "global", None, "42"
    ))

    assert st["preview_scope"] == "game"
    assert st["preview_appid"] == "42"
    assert st["contrast"] == 40


def test_stale_game_preview_cannot_leak_into_the_next_context(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_current_game("99"))
    color.applied.clear()

    st = asyncio.run(p.preview_calibration(
        {"contrast": 40}, "game", "42", "42"
    ))

    assert st["appid"] == "99" and st["preview"] is False
    assert color.applied == []


def test_stale_game_color_mutations_cannot_change_an_inactive_profile(
    tmp_path, monkeypatch
):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_current_game("99"))
    color.applied.clear()

    asyncio.run(p.set_saturation(180, "game", "42", "42"))
    asyncio.run(p.set_calibration(
        {"contrast": 40}, "game", "42", "42"
    ))
    asyncio.run(p.apply_color_preset("vivo", "game", "42", "42"))
    asyncio.run(p.preview_color_preset("vivo", "game", "42", "42"))
    asyncio.run(p.apply_oled_look("game", "42", "42"))
    asyncio.run(p.preview_oled_look("game", "42", "42"))
    asyncio.run(p.set_color_follow_global(False, "42", "42"))

    assert p._color.has_game("42") is False
    assert color.applied == []


def test_stale_color_reset_cannot_clear_the_active_profiles(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration({"contrast": 20}))
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_current_game("99"))
    color.applied.clear()

    st = asyncio.run(p.reset_color("42"))

    assert st["contrast"] == 20
    assert color.applied == []


def test_legacy_contextual_reset_still_saves_directly(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration({"contrast": 20}))
    asyncio.run(p.set_current_game("42"))

    st = asyncio.run(p.reset_color("42"))

    assert st["preview"] is False and st["contrast"] == 0
    restored, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(restored.get_color_state())["contrast"] == 0


def test_apply_oled_look_applies_a_vibrancy_boost(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.apply_oled_look())
    assert st["saturation"] > 100  # the generic look boosts vibrancy
    assert color.applied[-1]["saturation"] == st["saturation"]


def test_contextual_oled_look_is_previewed_before_persisting(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)

    st = asyncio.run(p.preview_oled_look("global", None, None))

    assert st["preview"] is True and st["saturation"] > 100
    restored, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(restored.get_color_state())["saturation"] == 100


def test_discard_contextual_preset_restores_saved_color(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_saturation(120, "global", None))
    asyncio.run(p.preview_color_preset("cine", "global", None, None))

    st = asyncio.run(p.discard_calibration(None))

    assert st["preview"] is False and st["saturation"] == 120
    assert color.applied[-1]["saturation"] == 120


def test_apply_native_preset_resets(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.apply_color_preset("vivo"))
    st = asyncio.run(p.apply_color_preset("native"))
    assert st["active_preset"] == "native"
    assert st["saturation"] == 100 and st["contrast"] == 0


def test_contextual_game_reset_only_changes_that_game_after_confirm(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_saturation(120, "global", None))
    asyncio.run(p.set_saturation(170, "game", "42"))
    asyncio.run(p.set_saturation(180, "game", "99"))
    asyncio.run(p.set_current_game("42"))

    preview = asyncio.run(p.reset_color("game", "42", "42"))
    assert preview["preview"] is True and preview["saturation"] == 100
    fields = (
        "saturation", "temperature", "contrast", "gamma", "hue",
        "black", "gain_r", "gain_g", "gain_b", "vibrance",
    )
    profile = {field: preview[field] for field in fields}
    asyncio.run(p.set_calibration(profile, "game", "42", "42"))

    assert p._color.effective("42")["saturation"] == 100
    assert p._color.effective("99")["saturation"] == 180
    assert p._color.effective(None)["saturation"] == 120


def test_night_mode_manual_overlay_applies_but_does_not_leak(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration({"temperature": 10}))     # the user's own temperature
    st = asyncio.run(p.set_night({"enabled": True, "schedule_enabled": False, "warmth": 50}))
    assert st["active"] is True and st["warmth"] == 50
    assert color.applied[-1]["temperature"] == 60           # 10 + 50 pushed to hardware
    # the warm shift must NOT leak into the reported calibration (slider keeps user's 10)
    assert asyncio.run(p.get_color_state())["temperature"] == 10


def test_night_state_persists(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_night({"schedule_enabled": True, "start": 1320, "end": 420, "warmth": 30}))
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p2.get_night_state())
    assert st["schedule_enabled"] is True and st["start"] == 1320 and st["warmth"] == 30


def test_set_hdr_persists(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_hdr({"enabled": True}))
    assert st["enabled"] is True
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_hdr_state())["enabled"] is True


def test_color_look_applies_regardless_of_hdr(tmp_path, monkeypatch):
    # The look colors all composited/SDR content even in HDR mode (only a native-HDR
    # game is out of reach, which needs no special handling), so it's applied either way.
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.get_hdr_state())                       # triggers _init
    p._device = dataclasses.replace(p._device, hdr=True)
    asyncio.run(p.apply_color_preset("cine"))            # an SDR look (saturation != 100)
    asyncio.run(p.set_hdr({"enabled": True}))
    assert color.applied[-1]["saturation"] != 100        # still applied with HDR on


class _LateColorBackend:
    """gamescope's Wayland socket comes up AFTER load: `supported` reads False until
    it has been polled `ready_after` times, then True (permanently). apply() records
    what got pushed."""

    def __init__(self, ready_after=2):
        self.ready_after = ready_after
        self._reads = 0
        self.probe_detail = "fake"
        self.force_composite = False
        self.applied = []

    @property
    def supported(self):
        self._reads += 1
        return self._reads > self.ready_after

    def apply(self, state):
        self.applied.append(dict(state))
        return True


def test_display_reapply_reasserts_multiple_times(tmp_path, monkeypatch):
    # gamescope can drop a look loaded during session bringup, so the waiter must
    # re-assert several times, not once.
    late = _LateColorBackend(ready_after=0)
    p, _ = _make_plugin(tmp_path, monkeypatch, color=late)
    asyncio.run(p.set_saturation(150, "global", None))
    late.applied.clear()
    asyncio.run(p._await_display_backend(
        attempts=2, interval=0, reasserts=4, reassert_interval=0))
    assert len(late.applied) == 4


def test_display_reapply_gives_up_without_gamescope(tmp_path, monkeypatch):
    # No gamescope (desktop): bounded — returns without ever applying (honest no-op).
    never = _LateColorBackend(ready_after=999)
    p, _ = _make_plugin(tmp_path, monkeypatch, color=never)
    asyncio.run(p.set_saturation(150, "global", None))
    never.applied.clear()
    asyncio.run(p._await_display_backend(attempts=3, interval=0))
    assert never.applied == []
