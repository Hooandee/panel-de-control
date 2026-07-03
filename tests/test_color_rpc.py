"""RPC-level tests for the Pantalla color controls.

Same Plugin bootstrap as test_cpu_rpc: fake decky + fake TDP backend so _init never
touches live hardware, plus a fake gamescope color backend so no real X display is
needed and we can assert what got applied.
"""
import asyncio
import importlib
import sys
import types


class _FakeColorBackend:
    def __init__(self, supported=True):
        self.supported = supported
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

    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)

    fake_color = color if color is not None else _FakeColorBackend()
    monkeypatch.setattr(main, "GamescopeColorBackend", lambda *a, **k: fake_color)
    return main.Plugin(), fake_color


def test_get_color_state_shape(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.get_color_state())
    assert st["supported"] is True
    for f in ("saturation", "temperature", "contrast"):
        assert f in st
    assert st["saturation"] == 100  # native by default
    assert "oled_look" in st and "appid" in st and "has_game_profile" in st


def test_set_saturation_global_applies(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_saturation(150, "global", None))
    assert st["saturation"] == 150
    assert color.applied[-1]["saturation"] == 150  # pushed to hardware


def test_saturation_per_game(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_saturation(120, "global", None))
    asyncio.run(p.set_current_game("42"))
    st = asyncio.run(p.set_saturation(170, "game", "42"))
    assert st["saturation"] == 170 and st["has_game_profile"] is True
    # global untouched
    asyncio.run(p.set_current_game(None))
    assert asyncio.run(p.get_color_state())["saturation"] == 120


def test_set_calibration_is_global(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_calibration(-40, 25))
    assert st["temperature"] == -40 and st["contrast"] == 25
    assert color.applied[-1]["contrast"] == 25
    assert st["preview"] is False  # confirmed → not pending


def test_preview_calibration_applies_live_but_does_not_persist(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.preview_calibration(-30, 40))
    assert st["preview"] is True  # pending confirmation
    assert st["temperature"] == -30 and st["contrast"] == 40
    assert color.applied[-1]["contrast"] == 40  # applied live to hardware
    # NOT persisted: a fresh instance sees native calibration
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["contrast"] == 0


def test_confirm_after_preview_persists(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.preview_calibration(-30, 40))
    asyncio.run(p.set_calibration(-30, 40))
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["contrast"] == 40  # saved


def test_auto_revert_drops_preview_and_reapplies_saved(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration(0, 20))       # saved baseline
    asyncio.run(p.preview_calibration(0, 60))   # unconfirmed preview
    assert asyncio.run(p.get_color_state())["contrast"] == 60
    p._do_color_revert()                         # timer fires
    st = asyncio.run(p.get_color_state())
    assert st["preview"] is False and st["contrast"] == 20  # back to saved
    assert color.applied[-1]["contrast"] == 20


def test_apply_oled_look_applies_a_vibrancy_boost(tmp_path, monkeypatch):
    p, color = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.apply_oled_look())
    assert st["saturation"] > 100  # the generic look boosts vibrancy
    assert color.applied[-1]["saturation"] == st["saturation"]


def test_reset_color_back_to_native(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_calibration(40, 20))
    asyncio.run(p.set_saturation(180, "global", None))
    st = asyncio.run(p.reset_color())
    assert st["saturation"] == 100 and st["contrast"] == 0 and st["temperature"] == 0


def test_unsupported_backend_degrades(tmp_path, monkeypatch):
    color = _FakeColorBackend(supported=False)
    p, _ = _make_plugin(tmp_path, monkeypatch, color=color)
    st = asyncio.run(p.get_color_state())
    assert st["supported"] is False
    # setting still persists + returns state, just no hardware apply
    st2 = asyncio.run(p.set_saturation(150, "global", None))
    assert st2["saturation"] == 150
    assert color.applied == []


def test_color_persists_across_instances(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_saturation(133, "global", None))
    p2, _ = _make_plugin(tmp_path, monkeypatch)
    assert asyncio.run(p2.get_color_state())["saturation"] == 133
