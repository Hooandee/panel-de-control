"""RPC-level coverage for the custom power-preset wiring in main.py. The store logic
is unit-tested in test_power_presets; this locks the glue (clamp to rails + atomic apply)."""
import asyncio

import pytest
from tdp.types import TdpLimits, TdpResult
from main_harness import fake_decky, load_main


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
    fake_decky(monkeypatch, tmp_path)
    from tdp import factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = load_main(monkeypatch)
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


def test_apply_three_watt_preset_preserves_request_and_applies_safe_minimum(Plugin):
    p = Plugin()

    result = asyncio.run(p.apply_power_preset(3, "global", None, None))

    assert result == {"requested_w": 3, "applied_w": 5, "ok": True, "detail": ""}
    state = asyncio.run(p.get_tdp_state())
    assert state["global_watts"] == 3
    assert state["global_levels"]["pl1"] == 5


def test_gpd_win_mini_presets_keep_low_requests_and_the_safe_ceiling(Plugin, monkeypatch):
    legacy = Plugin()
    low = asyncio.run(legacy.create_power_preset(3, "leaf", None))
    low_id = low["order"][-1]
    _use_gpd_win_mini(monkeypatch)

    migrated = Plugin()
    state = asyncio.run(migrated.get_power_presets())
    high = asyncio.run(migrated.create_power_preset(40, "bolt", None))
    high_id = high["order"][-1]

    assert state["custom"][low_id]["watts"] == 3
    assert high["custom"][high_id]["watts"] == 35


def test_apply_power_preset_unknown_scope_does_not_raise(Plugin):
    res = asyncio.run(Plugin().apply_power_preset(15, "bogus", None, None))
    assert res["ok"] is False and "unknown scope" in res["detail"]
