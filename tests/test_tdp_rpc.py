import asyncio
import dataclasses
import importlib
import sys
import types

import pytest

from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult

_FAKE_POWER = {"watts": 13.1, "gpu_busy": 49}


def _device_with_experimental_tdp_unlock():
    from device_profiles import DEVICE_TABLE

    device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    return dataclasses.replace(device, experimental_tdp_max_ac=55)


class FakeBackend:
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self._applied = None
        self._levels = None
        self.live_max = 60
        self.set_levels_calls = 0

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
        self.set_levels_calls += 1
        self._applied = min(pl1, self.live_max)
        self._levels = (self._applied, pl2, pl3)
        return TdpResult(pl1, self._applied, True, "")

    def read_applied(self):
        return self._applied

    def observe(self):
        if self._applied is None:
            return TdpObservation(
                readable=True,
                surfaces={
                    self.name: {
                        "pl1": RailReading(None, 5, self.live_max),
                        "pl2": RailReading(None, 5, 40),
                        "pl3": RailReading(None, 5, 50),
                    },
                },
            )
        pl2 = self._levels[1] if self._levels else self._applied
        pl3 = self._levels[2] if self._levels else self._applied
        return TdpObservation(
            readable=True,
            surfaces={
                self.name: {
                    "pl1": RailReading(
                        self._applied,
                        5,
                        self.live_max,
                    ),
                    "pl2": RailReading(pl2, 5, 40),
                    "pl3": RailReading(pl3, 5, 50),
                },
            },
        )

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


def _use_gpd_win_mini(monkeypatch):
    import main as main_module
    from device_profiles import DEVICE_TABLE

    device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    monkeypatch.setattr(main_module.device_registry, "detect", lambda *_a, **_k: device)
    monkeypatch.setattr(
        FakeBackend,
        "get_limits",
        lambda _self: TdpLimits(20, 20, 35, 35),
    )
    monkeypatch.setattr(FakeBackend, "level_limits", lambda _self: {})
    return main_module


def test_get_tdp_state_shape(Plugin):
    st = asyncio.run(Plugin().get_tdp_state())
    assert st["supported"] is True and st["backend"] == "fake"
    assert st["limits"] == {"min": 5, "default": 15, "max": 20, "max_ac": 60}
    assert st["request_min"] == 3
    assert "on_ac" in st and "watts" in st and "applied_w" in st
    assert "global_watts" in st and isinstance(st["global_watts"], int)
    assert st["requested_levels"] == {"pl1": 10, "pl2": 10, "pl3": 10}
    assert st["global_requested_levels"] == {"pl1": 10, "pl2": 10, "pl3": 10}
    # Presets fall back to the rail limits when the profile carries none, clamped
    # to [min, max_ac].
    assert st["presets"] == {"quiet": 5, "balanced": 15, "turbo": 20, "turbo_ac": 60}


def test_tdp_state_exposes_requested_target_and_applied(Plugin):
    p = Plugin()
    p._init()
    p._tdp_backend.live_max = 15
    asyncio.run(p.set_tdp_watts(25, "global"))
    st = asyncio.run(p.get_tdp_state())
    own = st["ownership"]
    assert own["requested"]["pl1"] == 25
    assert own["target"]["pl1"] == 15
    assert own["applied"]["pl1"] == 15
    assert own["status"] == "constrained"
    assert own["reason"] == "live_max"


def test_tdp_state_surfaces_are_structured(Plugin):
    p = Plugin()
    st = asyncio.run(p.get_tdp_state())
    assert isinstance(st["ownership"]["surfaces"], dict)
    assert "external_change" not in st


def test_set_tdp_watts_global_clamps_persists_applies(Plugin):
    p = Plugin()
    res = asyncio.run(p.set_tdp_watts(99, "global"))
    assert res["ok"] is True and res["applied_w"] == 60  # clamped to max_ac_w on charger
    st = asyncio.run(p.get_tdp_state())
    assert st["watts"] == 60
    # survives reload (persisted)
    assert asyncio.run(Plugin().get_tdp_state())["watts"] == 60


def test_manual_request_below_hardware_min_is_preserved_and_constrained(Plugin):
    p = Plugin()

    result = asyncio.run(p.set_tdp_watts(3, "global"))
    state = asyncio.run(p.get_tdp_state())

    assert result == {"requested_w": 3, "applied_w": 5, "ok": True, "detail": ""}
    assert state["global_watts"] == 3
    assert state["global_requested_levels"] == {"pl1": 3, "pl2": 3, "pl3": 3}
    assert state["global_levels"] == {"pl1": 5, "pl2": 5, "pl3": 5}
    assert state["ownership"]["requested"]["pl1"] == 3
    assert state["ownership"]["target"]["pl1"] == 5
    assert state["ownership"]["applied"]["pl1"] == 5
    assert state["ownership"]["status"] == "constrained"


def test_gpd_win_mini_normalizes_low_request_to_physical_floor(
    Plugin,
    monkeypatch,
):
    _use_gpd_win_mini(monkeypatch)
    p = Plugin()

    result = asyncio.run(p.set_tdp_watts(3, "global"))
    state = asyncio.run(p.get_tdp_state())

    assert result == {"requested_w": 20, "applied_w": 20, "ok": True, "detail": ""}
    assert state["request_min"] == 20
    assert state["global_watts"] == 20
    assert state["global_requested_levels"] == {"pl1": 20, "pl2": 20, "pl3": 20}
    assert state["ownership"]["status"] == "in_sync"


def test_gpd_win_mini_migrates_persisted_low_request(Plugin, monkeypatch):
    legacy = Plugin()
    asyncio.run(legacy.set_tdp_watts(3, "global"))
    _use_gpd_win_mini(monkeypatch)

    migrated = Plugin()
    state = asyncio.run(migrated.get_tdp_state())

    assert state["request_min"] == 20
    assert state["global_watts"] == 20
    assert migrated._tdp_profiles.effective(None)["pl1"] == 20


def test_gpd_win_mini_keeps_durable_limits_when_backend_is_unavailable(
    Plugin,
    monkeypatch,
):
    from tdp.backend import NullBackend

    legacy = Plugin()
    legacy._init()
    legacy._tdp_profiles.set_levels("global", 35, 35, 35)
    legacy._tdp_profiles.set_levels("game", 3, 3, 3, appid="low")
    main_module = _use_gpd_win_mini(monkeypatch)
    monkeypatch.setattr(
        main_module.tdp_factory,
        "select_backend",
        lambda *_a, **_k: NullBackend("temporarily unavailable"),
    )

    migrated = Plugin()
    migrated._init()

    assert migrated._profile_storage_limits() == TdpLimits(20, 20, 35, 35)
    assert migrated._tdp_request_min() == 20
    assert migrated._tdp_profiles.effective(None)["pl1"] == 35
    assert migrated._tdp_profiles.game_profile("low")["pl1"] == 20


def test_gpd_win_mini_profile_migration_retries_after_write_failure(
    Plugin,
    monkeypatch,
):
    import scoped_store

    legacy = Plugin()
    asyncio.run(legacy.set_tdp_watts(3, "global"))
    main_module = _use_gpd_win_mini(monkeypatch)
    original_save = scoped_store.atomic_json_save
    blocked = True
    clock = [0.0]

    monkeypatch.setattr(main_module, "_monotonic", lambda: clock[0])

    def flaky_save(path, data):
        if blocked and path.endswith("tdp_profiles.json"):
            raise OSError("disk unavailable")
        return original_save(path, data)

    monkeypatch.setattr(scoped_store, "atomic_json_save", flaky_save)
    migrated = Plugin()
    migrated._init()
    assert migrated._tdp_profiles.effective(None)["pl1"] == 20
    blocked_state = asyncio.run(migrated.get_tdp_state())
    assert blocked_state["global_watts"] == 20

    blocked = False
    clock[0] += main_module._TDP_STORAGE_MIGRATION_RETRY_S
    asyncio.run(migrated.get_tdp_state())

    reloaded = Plugin()
    reloaded._init()
    assert reloaded._tdp_profiles.effective(None)["pl1"] == 20


def test_manual_request_below_policy_floor_is_normalized_to_three(Plugin):
    p = Plugin()

    result = asyncio.run(p.set_tdp_watts(1, "global"))

    assert result["requested_w"] == 3
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 3


def test_manual_request_below_hardware_min_survives_reload(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(3, "global"))

    reloaded = Plugin()

    assert asyncio.run(reloaded.get_tdp_state())["global_watts"] == 3


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


def test_battery_state_caps_requested_rails_to_their_current_bounds(Plugin, monkeypatch):
    import main as main_module

    on_ac = True
    monkeypatch.setattr(main_module, "read_on_ac", lambda root="/": on_ac)
    p = Plugin()
    asyncio.run(p.set_tdp_watts(60, "global"))
    asyncio.run(p.set_tdp_levels(25, 25, "global"))

    on_ac = False
    state = asyncio.run(p.get_tdp_state())

    assert state["global_watts"] == 20
    assert state["global_requested_levels"] == {
        "pl1": 20,
        "pl2": 40,
        "pl3": 50,
    }


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
                             "ui_floor_engaged", "on_ac", "ownership"}
    assert r["ownership"] == asyncio.run(p.get_tdp_state())["ownership"]


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


def test_get_state_never_adopts_external_tdp(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(15, "global"))
    p._tdp_backend._applied = 30
    asyncio.run(p.get_tdp_state())
    asyncio.run(p.get_tdp_state())
    assert p._tdp_profiles.effective(None)["pl1"] == 15


def test_opening_qam_state_never_writes_hardware(Plugin):
    p = Plugin()
    asyncio.run(p.set_tdp_watts(15, "global"))
    p._tdp_backend.set_levels_calls = 0
    asyncio.run(p.get_tdp_state())
    asyncio.run(p.get_tdp_state())
    assert p._tdp_backend.set_levels_calls == 0


def test_cooler_boost_raises_ceiling_on_win5(Plugin):
    from device_registry import detect
    p = Plugin()
    p._init()
    p._device = detect(product_name="G1618-05")  # gpd_win5, cooler_max=75
    p._tdp_backend.get_limits = lambda: TdpLimits(5, 25, 55, 55)
    p._tdp_backend.level_limits = lambda: {
        "pl1": {"min": 5, "max": 75},
        "pl2": {"min": 5, "max": 75},
        "pl3": {"min": 5, "max": 75},
    }
    p._tdp_backend.cap_boost_to_active = True

    assert p._limits().max_w == 55 and p._limits().max_ac_w == 55
    assert asyncio.run(p.get_tdp_state())["level_limits"] == {
        "pl1": {"min": 5, "max": 55},
        "pl2": {"min": 5, "max": 55},
        "pl3": {"min": 5, "max": 55},
    }
    asyncio.run(p.set_cooler_boost(True))
    assert p._limits().max_w == 75 and p._limits().max_ac_w == 75  # cooler on
    assert asyncio.run(p.get_tdp_state())["level_limits"] == {
        "pl1": {"min": 5, "max": 75},
        "pl2": {"min": 5, "max": 75},
        "pl3": {"min": 5, "max": 75},
    }
    asyncio.run(p.set_cooler_boost(False))
    assert p._limits().max_w == 55


def test_cooler_boost_ignored_when_device_has_no_cooler(Plugin):
    p = Plugin()
    p._init()  # detected device is generic → cooler_max None
    asyncio.run(p.set_cooler_boost(True))
    assert p._limits().max_w == 20  # unchanged


def test_gpd_win_mini_does_not_offer_unvalidated_experimental_ceiling(Plugin):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._tdp_backend.get_limits = lambda: TdpLimits(20, 20, 35, 35)

    assert p._limits() == TdpLimits(20, 20, 35, 35)
    assert asyncio.run(p.get_experimental_tdp_unlock()) is False

    result = asyncio.run(p.set_experimental_tdp_unlock(True))

    assert result == {"enabled": False, "ok": True, "detail": "unchanged"}
    assert p._limits() == TdpLimits(20, 20, 35, 35)


def test_retired_gpd_unlock_is_not_forgotten_while_control_is_disabled(Plugin):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result == {
        "enabled": True,
        "ok": False,
        "detail": "TDP control disabled",
    }
    assert p._settings["experimental_tdp_unlock"] is True


def test_retired_gpd_unlock_is_cleared_only_after_safe_reapply(Plugin, monkeypatch):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    saves = []
    monkeypatch.setattr(p, "_save", lambda: saves.append(True))

    async def apply_safe(*_args, **_kwargs):
        return TdpResult(35, 35, True, "confirmed")

    monkeypatch.setattr(p, "_apply_tdp_now", apply_safe)

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result == {"enabled": False, "ok": True, "detail": "confirmed"}
    assert p._settings["experimental_tdp_unlock"] is False
    assert saves == [True]


def test_retired_gpd_unlock_survives_unconfirmed_safe_reapply(Plugin, monkeypatch):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True

    async def apply_unconfirmed(*_args, **_kwargs):
        return TdpResult(35, None, True, "applied (limit readback unavailable)")

    monkeypatch.setattr(p, "_apply_tdp_now", apply_unconfirmed)

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result["enabled"] is True
    assert result["ok"] is False
    assert "safe ceiling unconfirmed" in result["detail"]
    assert p._settings["experimental_tdp_unlock"] is True


def test_enabling_control_retires_gpd_unlock_after_safe_reapply(Plugin, monkeypatch):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    async def probe(*_args, **_kwargs):
        return True

    async def apply_safe(*_args, **_kwargs):
        return TdpResult(35, 35, True, "confirmed")

    monkeypatch.setattr(p, "_probe_tdp_backend", probe)
    monkeypatch.setattr(p, "_apply_tdp_now", apply_safe)

    assert asyncio.run(p.set_tdp_control_enabled(True)) is True
    assert p._settings["experimental_tdp_unlock"] is False


def test_enabling_control_rolls_back_when_gpd_reclamp_is_unconfirmed(
    Plugin,
    monkeypatch,
):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    async def probe(*_args, **_kwargs):
        return True

    async def apply_unconfirmed(*_args, **_kwargs):
        return TdpResult(35, None, True, "applied (limit readback unavailable)")

    monkeypatch.setattr(p, "_probe_tdp_backend", probe)
    monkeypatch.setattr(p, "_apply_tdp_now", apply_unconfirmed)
    monkeypatch.setattr(p, "_restore_power_handoff", lambda: True)

    assert asyncio.run(p.set_tdp_control_enabled(True)) is False
    assert p._settings["tdp_control_enabled"] is False
    assert p._settings["experimental_tdp_unlock"] is True


def test_ui_power_activation_uses_guarded_gpd_reclamp(Plugin, monkeypatch):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    async def probe(*_args, **_kwargs):
        return True

    async def apply_unconfirmed(*_args, **_kwargs):
        return TdpResult(35, None, True, "applied (limit readback unavailable)")

    monkeypatch.setattr(p, "_probe_tdp_backend", probe)
    monkeypatch.setattr(p, "_apply_tdp_now", apply_unconfirmed)
    monkeypatch.setattr(p, "_restore_power_handoff", lambda: True)

    state = asyncio.run(p.set_ui_module("power", False))

    assert "power" in state["disabled"]
    assert p._settings["tdp_control_enabled"] is False
    assert p._settings["experimental_tdp_unlock"] is True


def test_ui_power_activation_stays_off_when_gpd_backend_is_not_ready(
    Plugin,
    monkeypatch,
):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    async def probe(*_args, **_kwargs):
        return False

    monkeypatch.setattr(p, "_probe_tdp_backend", probe)
    monkeypatch.setattr(p, "_restore_power_handoff", lambda: True)

    state = asyncio.run(p.set_ui_module("power", False))

    assert "power" in state["disabled"]
    assert p._settings["tdp_control_enabled"] is False
    assert p._settings["experimental_tdp_unlock"] is True


def test_backend_without_auto_tdp_rejects_and_clears_stored_auto(PluginWithPower):
    p = PluginWithPower()
    p._init()
    p._tdp_backend.auto_tdp_supported = False
    p._tdp_profiles.set_auto_tdp("global", True)

    result = asyncio.run(p.set_auto_tdp(True))
    state = asyncio.run(p.get_tdp_state())
    power = asyncio.run(p.get_power_draw())

    assert result == {"auto_tdp": False}
    assert p._tdp_profiles.auto_tdp(None) is False
    assert state["supports_auto_tdp"] is False
    assert power["auto_tdp"] is False


def test_gpd_win_mini_corrupt_string_false_never_unlocks_55w(Plugin):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._tdp_backend.get_limits = lambda: TdpLimits(20, 20, 35, 35)
    p._settings["experimental_tdp_unlock"] = "false"

    assert asyncio.run(p.get_experimental_tdp_unlock()) is False
    assert p._limits() == TdpLimits(20, 20, 35, 35)


def test_gpd_win_mini_upgrade_normalizes_legacy_low_profile_intent(Plugin):
    from device_profiles import DEVICE_TABLE

    p = Plugin()
    p._init()
    p._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025"
    )
    p._tdp_backend.get_limits = lambda: TdpLimits(20, 20, 35, 35)
    p._tdp_backend.level_limits = lambda: {}
    p._tdp_profiles.set_levels("global", 10, 10, 10)

    storage = p._profile_storage_limits()
    changed = p._tdp_profiles.sanitize(storage.min_w, storage.max_ac_w)

    assert storage.min_w == 20
    assert changed is True
    assert p._tdp_profiles.effective(None)["pl1"] == 20
    assert p._effective_levels(None, on_ac=True)[0]["pl1"] == 20


def test_failed_experimental_disable_keeps_unlock_visibly_active(Plugin, monkeypatch):
    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    p._settings["experimental_tdp_unlock"] = True
    saves = []
    monkeypatch.setattr(p, "_save", lambda: saves.append(True))

    async def fail_apply(*_args, **_kwargs):
        return TdpResult(35, 55, False, "readback mismatch")

    monkeypatch.setattr(p, "_apply_tdp_now", fail_apply)

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result == {
        "enabled": True,
        "ok": False,
        "detail": "readback mismatch",
    }
    assert p._settings["experimental_tdp_unlock"] is True
    assert saves == []


def test_successful_experimental_disable_restarts_guard_after_runtime_lock_recovery(
    Plugin,
    monkeypatch,
):
    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    p._settings["experimental_tdp_unlock"] = True
    p._tdp_backend.supported = False
    p._tdp_backend.recover_safe_range = lambda: setattr(
        p._tdp_backend,
        "supported",
        True,
    ) or True
    starts = []
    monkeypatch.setattr(p, "_start_tdp_guard_loop", lambda: starts.append(True))

    async def apply_safe(*_args, **_kwargs):
        return TdpResult(35, 35, True, "")

    monkeypatch.setattr(p, "_apply_tdp_now", apply_safe)

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result["ok"] is True
    assert result["enabled"] is False
    assert starts == [True]


def test_failed_experimental_enable_reports_durable_unlock_if_rollback_save_fails(
    Plugin,
    monkeypatch,
):
    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    saves = 0

    def save():
        nonlocal saves
        saves += 1
        if saves == 2:
            raise OSError("disk unavailable")

    async def fail_apply(*_args, **_kwargs):
        return TdpResult(55, 35, False, "readback mismatch")

    monkeypatch.setattr(p, "_save", save)
    monkeypatch.setattr(p, "_apply_tdp_now", fail_apply)

    result = asyncio.run(p.set_experimental_tdp_unlock(True))

    assert result["enabled"] is True
    assert result["ok"] is False
    assert "rollback persist failed" in result["detail"]
    assert p._settings["experimental_tdp_unlock"] is True


def test_experimental_disable_requires_panel_ownership_to_confirm_safe_ceiling(Plugin):
    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    p._settings["experimental_tdp_unlock"] = True
    p._settings["tdp_control_enabled"] = False

    result = asyncio.run(p.set_experimental_tdp_unlock(False))

    assert result == {
        "enabled": True,
        "ok": False,
        "detail": "TDP control disabled",
    }
    assert p._settings["experimental_tdp_unlock"] is True


def test_experimental_unlock_keeps_automation_and_presets_at_base_ceiling(
    Plugin,
    monkeypatch,
):
    import main

    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    p._tdp_backend.get_limits = lambda: TdpLimits(20, 20, 35, 35)
    p._settings["experimental_tdp_unlock"] = True

    assert p._limits() == TdpLimits(20, 20, 35, 55)
    assert p._automatic_limits() == TdpLimits(20, 20, 35, 35)
    assert p._preset_wclamp() == (20, 35)
    assert max(p._tdp_presets(p._automatic_limits()).values()) == 35

    monkeypatch.setattr(main, "read_on_ac", lambda: True)
    result = asyncio.run(p.apply_power_preset(55, "global"))
    assert result["requested_w"] == 35
    assert p._tdp_profiles.effective(None)["pl1"] == 35


def test_manual_experimental_request_requires_ac(Plugin, monkeypatch):
    import main

    p = Plugin()
    p._init()
    p._device = _device_with_experimental_tdp_unlock()
    p._tdp_backend.get_limits = lambda: TdpLimits(20, 20, 35, 35)
    p._settings["experimental_tdp_unlock"] = True

    monkeypatch.setattr(main, "read_on_ac", lambda: False)
    battery = asyncio.run(p.set_tdp_watts(55, "global"))
    assert battery["requested_w"] == 35

    monkeypatch.setattr(main, "read_on_ac", lambda: True)
    charger = asyncio.run(p.set_tdp_watts(55, "global"))
    assert charger["requested_w"] == 55


def test_external_read_does_not_detach_a_follow_global_game(Plugin):
    p = Plugin()
    p._current_appid = "g"
    asyncio.run(p.set_tdp_watts(20, "game", "g"))
    asyncio.run(p.set_tdp_follow_global(True, "g"))
    assert p._tdp_profiles.is_following_global("g") is True
    p._tdp_backend._applied = 30
    asyncio.run(p.get_tdp_state())
    assert p._tdp_profiles.is_following_global("g") is True
