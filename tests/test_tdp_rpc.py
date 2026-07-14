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

    _profile = "custom"

    def profile_choices(self):
        return ["low-power", "balanced", "performance", "custom"]

    def read_profile(self):
        return self._profile

    def set_profile(self, mode):
        if mode in self.profile_choices():
            self._profile = mode
            return True
        return False


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
    # Presets fall back to the rail limits when the profile carries none, clamped
    # to [min, max_ac].
    assert st["presets"] == {"quiet": 5, "balanced": 15, "turbo": 20, "turbo_ac": 60}


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


def test_follow_global_toggle_applies_and_keeps_own(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_current_game("42"))
    asyncio.run(p.set_tdp_watts(10, "game", "42"))   # game's own value
    assert asyncio.run(p.get_tdp_state())["watts"] == 10
    st = asyncio.run(p.set_tdp_follow_global(True, "42"))  # follow global
    assert st["follows_global"] is True and st["watts"] == 20
    st = asyncio.run(p.set_tdp_follow_global(False, "42"))  # back to own, restored
    assert st["follows_global"] is False and st["watts"] == 10


def test_follow_own_on_game_without_profile_seeds_from_global(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(18, "global"))
    asyncio.run(p.set_current_game("99"))            # no own profile yet
    st = asyncio.run(p.set_tdp_follow_global(False, "99"))  # "use own" seeds from global
    assert st["follows_global"] is False
    assert st["has_game_profile"] is True
    assert st["watts"] == 18


def test_set_tdp_watts_game_without_appid_falls_back_to_global(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(20, "game", None))  # appid missing
    assert res["ok"] is True  # did not raise
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 20


def test_set_tdp_watts_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_watts(15, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def _force_legion(monkeypatch):
    import device_registry
    from device_profiles import DEVICE_TABLE
    legion = next(d for d in DEVICE_TABLE if d.key == "legion_go")
    monkeypatch.setattr(device_registry, "detect", lambda *a, **k: legion)


def test_firmware_modes_exposed_only_on_capable_device(Plugin, monkeypatch):
    _force_legion(monkeypatch)
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["firmware_modes"] == ["low-power", "balanced", "performance", "custom"]
    assert st["firmware_mode"] == "custom"  # default: our TDP owns the rails


def test_firmware_modes_absent_on_normal_device(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())  # generic detected device
    assert st["firmware_modes"] == []
    assert st["firmware_mode"] == "custom"


def test_set_firmware_mode_selects_and_persists(Plugin, monkeypatch):
    _force_legion(monkeypatch)
    p = Plugin()
    st = asyncio.run(p.set_tdp_firmware_mode("performance"))
    assert st["firmware_mode"] == "performance"
    # persists across reload (device-global setting) and is re-asserted on startup
    _force_legion(monkeypatch)
    assert asyncio.run(Plugin().get_tdp_state())["firmware_mode"] == "performance"


def test_moving_slider_leaves_firmware_mode(Plugin, monkeypatch):
    _force_legion(monkeypatch)
    p = Plugin()
    asyncio.run(p.set_tdp_firmware_mode("low-power"))
    asyncio.run(p.set_tdp_watts(15, "global"))
    assert asyncio.run(p.get_tdp_state())["firmware_mode"] == "custom"


def test_set_firmware_mode_rejects_unknown(Plugin, monkeypatch):
    _force_legion(monkeypatch)
    p = Plugin()
    st = asyncio.run(p.set_tdp_firmware_mode("turbo"))
    assert st["firmware_mode"] == "custom"  # unchanged


def test_state_exposes_advanced_fields(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supports_advanced"] is True
    assert st["level_limits"]["pl2"] == {"min": 5, "max": 40}  # uncapped (active_max=60 > 40)
    assert st["boost_mode"] == "estable"  # fresh profile is flat by default
    assert set(st["levels"]) == {"pl1", "pl2", "pl3"}
    assert "global_levels" in st and "global_boost_mode" in st


def test_set_tdp_levels_goes_manual_and_clamps(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))      # pl1 = 20, still estable
    res = asyncio.run(p.set_tdp_levels(8, 4, "global"))  # SPPT +8, FPPT +4
    assert res["ok"] is True
    st = asyncio.run(p.get_tdp_state())
    assert st["boost_mode"] == "custom"
    assert st["levels"]["pl2"] == 28 and st["levels"]["pl3"] == 32


def test_set_tdp_levels_clamps_to_rail_max(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(40, 40, "global"))  # 20+40=60 -> pl2 clamps to 40
    st = asyncio.run(p.get_tdp_state())
    # pl3: 20+40+40=100 -> clamped to rail max 50
    assert st["levels"]["pl2"] == 40 and st["levels"]["pl3"] == 50


def test_set_tdp_boost_mode_switches(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(20, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))
    assert asyncio.run(p.get_tdp_state())["boost_mode"] == "custom"
    # back to flat: rails collapse to PL1
    st = asyncio.run(p.set_tdp_boost_mode("estable", "global"))
    assert st["boost_mode"] == "estable"
    assert st["levels"]["pl2"] == 20 and st["levels"]["pl3"] == 20
    # auto: managed headroom
    st = asyncio.run(p.set_tdp_boost_mode("auto", "global"))
    assert st["boost_mode"] == "auto" and st["levels"]["pl2"] == 24  # round(20*1.2)


def test_set_tdp_watts_preserves_custom_margins(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(17, "global"))
    asyncio.run(p.set_tdp_levels(8, 4, "global"))   # custom: pl2=25, pl3=29
    asyncio.run(p.set_tdp_watts(22, "global"))      # raise pl1, keep margins
    st = asyncio.run(p.get_tdp_state())
    assert st["boost_mode"] == "custom"
    assert st["levels"]["pl2"] == 30 and st["levels"]["pl3"] == 34


def test_set_tdp_levels_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().set_tdp_levels(8, 4, "bogus"))
    assert res["ok"] is False and "unknown scope" in res["detail"]


def test_set_tdp_boost_mode_unknown_scope_is_noop_state(Plugin):
    # Invalid scope is a no-op but must still return a valid TdpState (the frontend
    # applies the result via setTdp), not an error dict that would corrupt the UI.
    st = asyncio.run(Plugin().set_tdp_boost_mode("estable", "bogus"))
    assert "supported" in st and "levels" in st and "limits" in st


def test_battery_ceiling_caps_pl1_not_boost_rails(Plugin, monkeypatch):
    import main as main_module
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": False)
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(99, "global"))
    assert res["applied_w"] == 20  # PL1 clamped to battery max, not charger 60
    st = asyncio.run(p.get_tdp_state())
    assert st["on_ac"] is False
    assert st["watts"] == 20
    assert st["level_limits"]["pl1"]["max"] == 20  # PL1 (sustained) capped to battery
    # Boost rails keep their firmware max so the additive SPPT/FPPT offsets are still
    # movable above PL1 (the bug: at PL1=max they collapsed to a 0-width range).
    assert st["level_limits"]["pl2"]["max"] == 40
    assert st["level_limits"]["pl3"]["max"] == 50


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
    assert set(r.keys()) == {"watts", "gpu_busy", "auto_tdp", "setpoint", "applied",
                             "ui_floor_engaged"}


def test_get_power_draw_values(PluginWithPower):
    p = PluginWithPower()
    r = asyncio.run(p.get_power_draw())
    assert r["watts"] == 13.1
    assert r["gpu_busy"] == 49
    assert r["auto_tdp"] is False  # default off
    assert isinstance(r["setpoint"], int)  # effective clamped pl1
    assert r["applied"] is None or isinstance(r["applied"], int)  # live firmware PL1


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


# --- telemetry RPC tests -------------------------------------------------------

def test_get_telemetry_no_game_returns_empty_shape(Plugin):
    p = Plugin()
    r = asyncio.run(p.get_telemetry())
    assert set(r.keys()) == {"samples_n", "by_pl1", "recent"}
    assert r["samples_n"] == 0
    assert r["by_pl1"] == {}
    assert r["recent"] == []


def test_get_telemetry_with_explicit_appid_unknown_returns_empty(Plugin):
    p = Plugin()
    r = asyncio.run(p.get_telemetry(appid="99999"))
    assert r["samples_n"] == 0


def test_collect_sample_returns_none_without_game(Plugin):
    p = Plugin()
    p._init()
    assert p._collect_sample() is None


def test_collect_sample_returns_tuple_with_game(Plugin, monkeypatch):
    import main as main_module
    import types

    fake_pr = types.SimpleNamespace(read=lambda: {"watts": 11.0, "gpu_busy": 60})
    fake_fan = types.SimpleNamespace(read=lambda: {
        "supported": True,
        "fans": [{"label": "cpu_fan", "rpm": 1800, "percent": 50}],
        "temps": [
            {"label": "CPU", "celsius": 52.0},
            {"label": "GPU", "celsius": 48.0},
        ],
    })

    original_init = main_module.Plugin._init

    def patched_init(self):
        original_init(self)
        self._power_reader = fake_pr
        self._fan_reader = fake_fan

    monkeypatch.setattr(main_module.Plugin, "_init", patched_init)

    p = main_module.Plugin()
    p._init()
    p._current_appid = "42"
    result = p._collect_sample()
    assert result is not None
    appid, sample = result
    assert appid == "42"
    assert sample["pl1"] is not None
    assert sample["watts"] == 11.0
    assert sample["gpu_busy"] == 60
    assert sample["temp_cpu"] == pytest.approx(52.0)
    assert sample["temp_gpu"] == pytest.approx(48.0)
    assert sample["fan_rpm"] == 1800


def test_get_telemetry_aggregates_after_collect(Plugin, monkeypatch):
    import main as main_module
    import types

    fake_pr = types.SimpleNamespace(read=lambda: {"watts": 13.0, "gpu_busy": 75})
    fake_fan = types.SimpleNamespace(read=lambda: {
        "supported": True,
        "fans": [{"label": "cpu_fan", "rpm": 2000, "percent": 60}],
        "temps": [
            {"label": "CPU", "celsius": 55.0},
            {"label": "GPU", "celsius": 50.0},
        ],
    })

    original_init = main_module.Plugin._init

    def patched_init(self):
        original_init(self)
        self._power_reader = fake_pr
        self._fan_reader = fake_fan

    monkeypatch.setattr(main_module.Plugin, "_init", patched_init)

    p = main_module.Plugin()
    p._init()
    p._current_appid = "42"
    # Manually collect a sample into the store (bypasses asyncio)
    result = p._collect_sample()
    assert result is not None
    appid, sample = result
    p._telemetry.add_sample(appid, sample, dt=5.0)

    agg = asyncio.run(p.get_telemetry())
    assert agg["samples_n"] == 1
    assert len(agg["recent"]) == 1


def test_adopt_external_tdp_syncs_and_flags(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(15, "global"))
    p._tdp_backend._applied = 18  # HHD/Steam moved the firmware PL1 behind our back
    st = asyncio.run(p.get_tdp_state())
    assert st["external_change"] is True
    assert st["global_watts"] == 18  # adopted → our setpoint follows, no stomp next reapply
    # already adopted → a second read is no longer flagged
    assert asyncio.run(p.get_tdp_state())["external_change"] is False


def test_adopt_skipped_in_download_mode(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(15, "global"))
    asyncio.run(p.set_eco(True, 50))
    assert p._adopt_external_tdp(18) is False  # eco owns the setpoint (forced min)


def test_adopt_skipped_within_threshold(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(15, "global"))
    assert p._adopt_external_tdp(16) is False  # 1 W jitter, not an external change


def test_no_adopt_before_first_apply(Plugin):
    # Startup race: the firmware still holds a default before we've applied our saved
    # profile — it must NOT be mistaken for an external change and overwrite the profile.
    p = Plugin()
    asyncio.run(p.get_tdp_state())  # init backends; nothing applied yet
    p._tdp_backend._applied = 28    # firmware default, we've written nothing
    st = asyncio.run(p.get_tdp_state())
    assert st["external_change"] is False


def test_cooler_boost_raises_ceiling_on_win5(Plugin):
    from device_registry import detect
    p = Plugin()
    p._init()
    p._device = detect(product_name="G1618-05")  # gpd_win5, cooler_max=75
    assert p._limits().max_w == 20 and p._limits().max_ac_w == 60  # cooler off
    asyncio.run(p.set_cooler_boost(True))
    assert p._limits().max_w == 75 and p._limits().max_ac_w == 75  # cooler on
    asyncio.run(p.set_cooler_boost(False))
    assert p._limits().max_w == 20


def test_cooler_boost_ignored_when_device_has_no_cooler(Plugin):
    p = Plugin()
    p._init()  # detected device is generic → cooler_max None
    asyncio.run(p.set_cooler_boost(True))
    assert p._limits().max_w == 20  # unchanged


def test_adopt_does_not_detach_a_follow_global_game(Plugin):
    # A game that kept its own stored profile but is toggled back to following global
    # must NOT be silently detached when an external tool moves PL1 (the adopt path
    # writes to the live scope = global here, never flipping follow_global off).
    p = Plugin()
    p._current_appid = "g"
    asyncio.run(p.set_tdp_watts(20, "game", "g"))
    asyncio.run(p.set_tdp_follow_global(True, "g"))
    assert p._tdp_profiles.is_following_global("g") is True
    p._tdp_backend._applied = 30  # external tool moved the firmware PL1
    asyncio.run(p.get_tdp_state())  # triggers adoption
    assert p._tdp_profiles.is_following_global("g") is True  # still following, not detached
