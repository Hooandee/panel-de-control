"""RPC-level coverage for the custom power-preset wiring in main.py. The store logic
is unit-tested in test_power_presets; this locks the glue (clamp to rails + atomic apply)."""
import asyncio
import importlib
import sys
import types

import pytest
from tdp.types import TdpLimits, TdpResult


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
    from tdp import factory
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


def test_get_power_presets_fresh_shape(Plugin):
    st = asyncio.run(Plugin().get_power_presets())
    assert st["order"] == ["quiet", "balanced", "turbo"]
    assert st["hidden"] == [] and st["custom"] == {}


def test_create_clamps_watts_to_active_ceiling(Plugin):
    p = Plugin()
    st = asyncio.run(p.create_power_preset(999, "bolt", None))
    cid = st["order"][-1]
    assert st["custom"][cid]["watts"] == 60
    st = asyncio.run(p.create_power_preset(1, "leaf", None))
    cid = st["order"][-1]
    assert st["custom"][cid]["watts"] == 3


def test_crud_and_hide_roundtrip_persists(Plugin):
    p = Plugin()
    st = asyncio.run(p.create_power_preset(12, "bolt", None))
    cid = st["order"][-1]
    st = asyncio.run(p.update_power_preset(cid, 14, "leaf", None, "Emu"))
    assert st["custom"][cid] == {"watts": 14, "icon": "leaf", "name": "Emu",
                                 "boost": {"mode": "estable", "off2": 0, "off3": 0}}
    st = asyncio.run(p.set_power_preset_hidden("quiet", True))
    assert "quiet" in st["hidden"]
    st = asyncio.run(p.move_power_preset("turbo", -1))
    assert st["order"].index("turbo") < st["order"].index("balanced")
    # survives a fresh Plugin (persisted to disk)
    assert asyncio.run(Plugin().get_power_presets())["custom"][cid]["watts"] == 14
    st = asyncio.run(p.delete_power_preset(cid))
    assert cid not in st["custom"]


def test_apply_power_preset_sets_watts_on_scope(Plugin):
    p = Plugin()
    res = asyncio.run(p.apply_power_preset(18, "global", None, None))
    assert res["ok"] is True and res["applied_w"] == 18
    assert asyncio.run(p.get_tdp_state())["global_watts"] == 18


def test_apply_three_watt_preset_preserves_request_and_applies_safe_minimum(Plugin):
    p = Plugin()

    result = asyncio.run(p.apply_power_preset(3, "global", None, None))

    assert result == {"requested_w": 3, "applied_w": 5, "ok": True, "detail": ""}
    state = asyncio.run(p.get_tdp_state())
    assert state["global_watts"] == 3
    assert state["global_levels"]["pl1"] == 5


def test_three_watt_custom_preset_survives_reload_on_other_devices(Plugin):
    p = Plugin()
    state = asyncio.run(p.create_power_preset(3, "leaf", None))
    preset_id = state["order"][-1]

    reloaded = asyncio.run(Plugin().get_power_presets())

    assert reloaded["custom"][preset_id]["watts"] == 3


def test_gpd_win_mini_normalizes_new_and_stored_low_presets(Plugin, monkeypatch):
    legacy = Plugin()
    legacy_state = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    preset_id = legacy_state["order"][-1]
    _use_gpd_win_mini(monkeypatch)

    migrated = Plugin()
    state = asyncio.run(migrated.get_power_presets())
    new_state = asyncio.run(migrated.create_power_preset(3, "leaf", None))
    new_id = new_state["order"][-1]

    assert state["custom"][preset_id]["watts"] == 20
    assert new_state["custom"][new_id]["watts"] == 20


def test_gpd_win_mini_preserves_preset_range_when_backend_is_unavailable(
    Plugin,
    monkeypatch,
):
    from tdp.backend import NullBackend

    legacy = Plugin()
    low = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    low_id = low["order"][-1]
    high = asyncio.run(legacy.create_power_preset(35, "bolt", None))
    high_id = high["order"][-1]
    main_module = _use_gpd_win_mini(monkeypatch)
    monkeypatch.setattr(
        main_module.tdp_factory,
        "select_backend",
        lambda *_a, **_k: NullBackend("temporarily unavailable"),
    )

    migrated = Plugin()
    state = asyncio.run(migrated.get_power_presets())
    created = asyncio.run(migrated.create_power_preset(35, "bolt", None))
    created_id = created["order"][-1]

    assert state["custom"][low_id]["watts"] == 20
    assert state["custom"][high_id]["watts"] == 35
    assert created["custom"][created_id]["watts"] == 35


def test_gpd_win_mini_preset_migration_retries_after_write_failure(
    Plugin,
    monkeypatch,
):
    import power_presets

    legacy = Plugin()
    legacy_state = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    preset_id = legacy_state["order"][-1]
    main_module = _use_gpd_win_mini(monkeypatch)
    original_save = power_presets.atomic_json_save
    blocked = True
    attempts = 0
    clock = [0.0]

    monkeypatch.setattr(main_module, "_monotonic", lambda: clock[0])

    def flaky_save(path, data):
        nonlocal attempts
        if blocked and path.endswith("power_presets.json"):
            attempts += 1
            raise OSError("disk unavailable")
        return original_save(path, data)

    monkeypatch.setattr(power_presets, "atomic_json_save", flaky_save)
    migrated = Plugin()
    migrated._init()
    state = asyncio.run(migrated.get_power_presets())
    assert state["custom"][preset_id]["watts"] == 20
    asyncio.run(migrated.get_power_presets())
    assert attempts == 1

    blocked = False
    clock[0] += main_module._TDP_STORAGE_MIGRATION_RETRY_S
    asyncio.run(migrated.get_power_presets())

    reloaded = Plugin()
    assert asyncio.run(reloaded.get_power_presets())["custom"][preset_id]["watts"] == 20


def test_gpd_win_mini_crud_persists_pending_preset_migration(
    Plugin,
    monkeypatch,
):
    import power_presets

    legacy = Plugin()
    legacy_state = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    legacy_id = legacy_state["order"][-1]
    main_module = _use_gpd_win_mini(monkeypatch)
    original_save = power_presets.atomic_json_save
    failures_remaining = 2
    attempts = 0
    clock = [0.0]

    monkeypatch.setattr(main_module, "_monotonic", lambda: clock[0])

    def flaky_save(path, data):
        nonlocal attempts, failures_remaining
        if path.endswith("power_presets.json"):
            attempts += 1
            if failures_remaining:
                failures_remaining -= 1
                raise OSError("disk unavailable")
        return original_save(path, data)

    monkeypatch.setattr(power_presets, "atomic_json_save", flaky_save)
    migrated = Plugin()
    migrated._init()
    clock[0] += main_module._TDP_STORAGE_MIGRATION_RETRY_S

    created = asyncio.run(migrated.create_power_preset(25, "bolt", None))
    created_id = created["order"][-1]
    on_disk = power_presets.PowerPresetStore(
        migrated._power_presets._path
    ).state()

    assert attempts == 3
    assert on_disk["custom"][legacy_id]["watts"] == 20
    assert on_disk["custom"][created_id]["watts"] == 25


def test_gpd_win_mini_failed_crud_keeps_pending_migration_sanitized(
    Plugin,
    monkeypatch,
):
    import power_presets

    legacy = Plugin()
    legacy_state = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    legacy_id = legacy_state["order"][-1]
    _use_gpd_win_mini(monkeypatch)
    original_save = power_presets.atomic_json_save
    failures_remaining = 2

    def flaky_save(path, data):
        nonlocal failures_remaining
        if path.endswith("power_presets.json") and failures_remaining:
            failures_remaining -= 1
            raise OSError("disk unavailable")
        return original_save(path, data)

    monkeypatch.setattr(power_presets, "atomic_json_save", flaky_save)
    migrated = Plugin()
    migrated._init()

    with pytest.raises(OSError, match="disk unavailable"):
        asyncio.run(migrated.create_power_preset(25, "bolt", None))
    created = asyncio.run(migrated.create_power_preset(30, "bolt", None))
    created_id = created["order"][-1]
    on_disk = power_presets.PowerPresetStore(
        migrated._power_presets._path
    ).state()

    assert on_disk["custom"][legacy_id]["watts"] == 20
    assert on_disk["custom"][created_id]["watts"] == 30


def test_apply_power_preset_with_boost_sets_custom_rails(Plugin):
    p = Plugin()
    res = asyncio.run(p.apply_power_preset(
        20, "global", None, {"mode": "custom", "off2": 8, "off3": 4}))
    assert res["ok"] is True
    st = asyncio.run(p.get_tdp_state())
    assert st["global_boost_mode"] == "custom"
    assert st["global_levels"]["pl2"] == 28 and st["global_levels"]["pl3"] == 32


def test_apply_power_preset_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().apply_power_preset(15, "bogus", None, None))
    assert res["ok"] is False and "unknown scope" in res["detail"]
