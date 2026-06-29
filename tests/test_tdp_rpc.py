import asyncio
import importlib
import sys
import types

import pytest

from tdp.types import TdpLimits, TdpResult

_FAKE_POWER = {"watts": 13.1, "gpu_busy": 49}


class FakeBackend:
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self._applied = None
        self._levels = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 60},
                "pl2": {"min": 5, "max": 40},
                "pl3": {"min": 5, "max": 50}}

    def set_tdp(self, watts, ac):
        self._applied = watts
        return TdpResult(watts, watts, True, "")

    def set_levels(self, pl1, pl2, pl3, ac):
        self._applied = pl1
        self._levels = (pl1, pl2, pl3)
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "decky", fake)
    import tdp.factory as factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


def test_get_tdp_state_shape(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supported"] is True and st["backend"] == "fake"
    assert st["limits"] == {"min": 5, "default": 15, "max": 20, "max_ac": 60}
    assert "on_ac" in st and "watts" in st and "applied_w" in st
    assert "global_watts" in st and isinstance(st["global_watts"], int)


def test_set_tdp_watts_global_clamps_persists_applies(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(99, "global"))
    assert res["ok"] is True and res["applied_w"] == 60  # clamped to max_ac_w on charger
    st = asyncio.run(p.get_tdp_state())
    assert st["watts"] == 60
    # survives reload (persisted)
    assert asyncio.run(Plugin().get_tdp_state())["watts"] == 60


def test_per_game_profile_overrides_global(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.create_game_profile("42"))
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_tdp_watts(10, "game", "42"))
    st = asyncio.run(p.get_tdp_state())
    assert st["watts"] == 10
    assert st["global_watts"] == 20
    asyncio.run(p.set_current_game(None))
    assert asyncio.run(p.get_tdp_state())["watts"] == 20


def test_set_tdp_watts_game_without_appid_falls_back_to_global(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(20, "game", None))  # appid missing
    assert res["ok"] is True  # did not raise
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 20


def test_set_tdp_watts_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_watts(15, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_state_exposes_advanced_fields(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supports_advanced"] is True
    assert st["level_limits"]["pl2"] == {"min": 5, "max": 40}  # uncapped (active_max=60 > 40)
    assert st["auto"] is True  # fresh profile is auto
    assert set(st["levels"]) == {"pl1", "pl2", "pl3"}
    assert "global_levels" in st and "global_auto" in st


def test_set_tdp_levels_goes_manual_and_clamps(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))      # pl1 = 20, still auto
    res = asyncio.run(p.set_tdp_levels(8, 4, "global"))  # SPPT +8, FPPT +4
    assert res["ok"] is True
    st = asyncio.run(p.get_tdp_state())
    assert st["auto"] is False
    assert st["levels"]["pl2"] == 28 and st["levels"]["pl3"] == 32


def test_set_tdp_levels_clamps_to_rail_max(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(40, 40, "global"))  # 20+40=60 -> pl2 clamps to 40
    st = asyncio.run(p.get_tdp_state())
    # pl3: 20+40+40=100 -> clamped to rail max 50
    assert st["levels"]["pl2"] == 40 and st["levels"]["pl3"] == 50


def test_reset_tdp_auto_reverts(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))
    assert asyncio.run(p.get_tdp_state())["auto"] is False
    asyncio.run(p.reset_tdp_auto("global"))
    assert asyncio.run(p.get_tdp_state())["auto"] is True


def test_set_tdp_watts_preserves_manual_margins(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(17, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))   # manual: pl2=25, pl3=29
    asyncio.run(p.set_tdp_watts(22, "global"))      # raise pl1, keep margins
    st = asyncio.run(p.get_tdp_state())
    assert st["auto"] is False
    assert st["levels"]["pl2"] == 30 and st["levels"]["pl3"] == 34


def test_set_tdp_levels_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_levels(8, 4, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_reset_tdp_auto_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().reset_tdp_auto("bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_battery_ceiling_caps_pl1_and_rails(Plugin, monkeypatch):
    import main as main_module
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(99, "global"))
    assert res["applied_w"] == 20  # clamped to battery max, not charger 60
    st = asyncio.run(p.get_tdp_state())
    assert st["on_ac"] is False
    assert st["watts"] == 20
    assert st["level_limits"]["pl2"]["max"] == 20  # rails capped to battery ceiling
    assert st["levels"]["pl2"] == 20


# --- auto-TDP RPC tests -------------------------------------------------------

@pytest.fixture
def PluginWithPower(Plugin, monkeypatch):
    """Plugin fixture with a deterministic fake PowerReader."""
    import main as main_module
    fake_pr = types.SimpleNamespace(read=lambda: dict(_FAKE_POWER))
    # Patch _init so it installs our fake reader, then call _init normally.
    original_init = main_module.Plugin._init

    def patched_init(self):
        original_init(self)
        self._power_reader = fake_pr

    monkeypatch.setattr(main_module.Plugin, "_init", patched_init)
    return main_module.Plugin


def test_get_power_draw_has_all_keys(PluginWithPower):
    p = PluginWithPower()
    r = asyncio.run(p.get_power_draw())
    assert set(r.keys()) == {"watts", "gpu_busy", "auto_tdp", "setpoint", "fps", "target_fps"}


def test_get_power_draw_values(PluginWithPower):
    p = PluginWithPower()
    r = asyncio.run(p.get_power_draw())
    assert r["watts"] == 13.1
    assert r["gpu_busy"] == 49
    assert r["auto_tdp"] is False  # default off
    assert isinstance(r["setpoint"], int)  # effective clamped pl1


def test_set_auto_tdp_true_returns_correct_shape(PluginWithPower):
    p = PluginWithPower()
    res = asyncio.run(p.set_auto_tdp(True))
    assert res == {"auto_tdp": True}


def test_set_auto_tdp_false_returns_correct_shape(PluginWithPower):
    p = PluginWithPower()
    asyncio.run(p.set_auto_tdp(True))
    res = asyncio.run(p.set_auto_tdp(False))
    assert res == {"auto_tdp": False}


def test_set_auto_tdp_persists_across_rpc_calls(PluginWithPower):
    p = PluginWithPower()
    asyncio.run(p.set_auto_tdp(True))
    r = asyncio.run(p.get_power_draw())
    assert r["auto_tdp"] is True


def test_get_power_draw_auto_tdp_false_by_default(PluginWithPower):
    p = PluginWithPower()
    r = asyncio.run(p.get_power_draw())
    assert r["auto_tdp"] is False


# --- FPS-target RPC tests -----------------------------------------------------

class FakeGamescope:
    """Minimal fake for GamescopeStats used in Plugin tests."""

    def __init__(self, fps=None, focus=None):
        self._fps = fps
        self._focus = focus

    def start(self):
        pass

    def stop(self):
        pass

    def game_fps(self):
        # Only return fps when focus is a real (numeric) appid
        if self._focus is None or self._focus == "steam":
            return None
        return self._fps

    def read(self):
        fps = self.game_fps()
        return {"fps": fps, "focus": self._focus}


@pytest.fixture
def PluginWithFPS(Plugin, monkeypatch):
    """Plugin fixture with fake PowerReader AND fake GamescopeStats."""
    import main as main_module
    fake_pr = types.SimpleNamespace(read=lambda: dict(_FAKE_POWER))
    fake_gs = FakeGamescope(fps=72.0, focus="3768760")
    original_init = main_module.Plugin._init

    def patched_init(self):
        original_init(self)
        self._power_reader = fake_pr
        self._gamescope = fake_gs

    monkeypatch.setattr(main_module.Plugin, "_init", patched_init)
    return main_module.Plugin


def test_get_power_draw_includes_fps_and_target(PluginWithFPS):
    p = PluginWithFPS()
    r = asyncio.run(p.get_power_draw())
    assert "fps" in r
    assert "target_fps" in r


def test_get_power_draw_fps_value_from_gamescope(PluginWithFPS):
    p = PluginWithFPS()
    r = asyncio.run(p.get_power_draw())
    assert abs(r["fps"] - 72.0) < 1e-4


def test_get_power_draw_target_fps_none_by_default(PluginWithFPS):
    p = PluginWithFPS()
    r = asyncio.run(p.get_power_draw())
    assert r["target_fps"] is None


def test_set_fps_target_stores_and_returns(PluginWithFPS):
    p = PluginWithFPS()
    res = asyncio.run(p.set_fps_target(50))
    assert res == {"target_fps": 50}
    r = asyncio.run(p.get_power_draw())
    assert r["target_fps"] == 50


def test_set_fps_target_none_clears(PluginWithFPS):
    p = PluginWithFPS()
    asyncio.run(p.set_fps_target(60))
    res = asyncio.run(p.set_fps_target(None))
    assert res == {"target_fps": None}
    r = asyncio.run(p.get_power_draw())
    assert r["target_fps"] is None


def test_set_fps_target_persists(PluginWithFPS):
    p = PluginWithFPS()
    asyncio.run(p.set_fps_target(30))
    # same instance — persisted to settings dict
    r = asyncio.run(p.get_power_draw())
    assert r["target_fps"] == 30


def test_get_power_draw_full_shape(PluginWithFPS):
    p = PluginWithFPS()
    r = asyncio.run(p.get_power_draw())
    assert set(r.keys()) == {"watts", "gpu_busy", "auto_tdp", "setpoint", "fps", "target_fps"}


def test_get_power_draw_steam_focus_returns_none_fps(Plugin, monkeypatch):
    """When gamescope focus is 'steam', fps must be None in the RPC response."""
    import main as main_module
    fake_pr = types.SimpleNamespace(read=lambda: dict(_FAKE_POWER))
    fake_gs = FakeGamescope(fps=60.0, focus="steam")
    original_init = main_module.Plugin._init

    def patched_init(self):
        original_init(self)
        self._power_reader = fake_pr
        self._gamescope = fake_gs

    monkeypatch.setattr(main_module.Plugin, "_init", patched_init)
    p = main_module.Plugin()
    r = asyncio.run(p.get_power_draw())
    assert r["fps"] is None
