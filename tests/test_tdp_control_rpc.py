"""RPC-level coverage for the TDP control master switch + HHD take/release:
the conflict readout, taking control from HHD (reversible, saving the previous
value), the master switch gating every TDP write, and restoring HHD on release
/ teardown.
"""
import asyncio
import importlib
import json
import sys
import types

import pytest

from device_profiles import DEVICE_TABLE
from tdp.factory import select_backend as real_select_backend
from tdp.types import TdpLimits, TdpResult


class FakeBackend:
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self.set_levels_calls = 0
        self.release_calls = 0
        self.release_ok = True
        self._applied = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 35}}

    def set_levels(self, pl1, pl2, pl3, ac):
        self.set_levels_calls += 1
        self._applied = pl1
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied

    def release(self):
        self.release_calls += 1
        return self.release_ok


class FakeFan:
    supported = True
    name = "fake-fan"

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255, "fans": []}

    def apply_curve_all(self, points):
        pass

    def set_auto(self, points):
        pass

    def restore_auto(self):
        pass


class FakeHHD:
    """Stand-in for the controllers.hhd module functions."""
    def __init__(self, value=True):
        self.value = value

    def set(self, v):
        self.value = v

    def current_tdp_enable(self, root="/"):
        return self.value

    def set_tdp_enable(self, enabled, root="/"):
        self.value = bool(enabled)
        return self.value


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
    import fans.control as fan_control
    monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


def test_profile_storage_limits_ignore_temporary_flow_firmware_ceiling(Plugin):
    plugin = Plugin.__new__(Plugin)
    plugin._device = next(
        profile for profile in DEVICE_TABLE if profile.key == "rog_flow_z13"
    )
    plugin._settings = {"cooler_boost": False, "unlock_battery_max": False}
    plugin._tdp_backend = types.SimpleNamespace(
        get_limits=lambda: TdpLimits(5, 20, 42, 42),
    )

    assert plugin._limits().max_ac_w == 42
    assert plugin._profile_storage_limits().max_ac_w == 65


def test_dynamic_backend_readiness_controls_published_tdp_support(Plugin):
    plugin = Plugin.__new__(Plugin)
    plugin._tdp_backend = types.SimpleNamespace(supported=True, ready=lambda: False)

    assert plugin._tdp_supported() is False

    plugin._tdp_backend.ready = lambda: True
    assert plugin._tdp_supported() is True


def test_bazzite_legion_go_2_recovers_a_startup_lock_after_sysfs_appears(
    Plugin,
    tmp_path,
):
    lock_path = (
        tmp_path
        / "run/panel-de-control/firmware-lenovo-wmi-other.lock"
    )
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps({
            "state": "transaction_pending",
            "detail": "firmware transaction pending",
            "snapshot": {
                "firmware-attr:lenovo-wmi-other/pl1": 12,
                "firmware-attr:lenovo-wmi-other/pl2": 18,
                "firmware-attr:lenovo-wmi-other/pl3": 24,
            },
            "profile": "balanced",
        }),
        encoding="utf-8",
    )
    device = next(
        profile for profile in DEVICE_TABLE if profile.key == "legion_go_2"
    )
    backend = real_select_backend(
        device,
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/bin/true",
        os_id="bazzite",
    )
    assert backend.name == "firmware-attr:lenovo-wmi-other"
    assert backend.supported is False
    assert backend.safety_locked is True

    plugin = Plugin()
    plugin._init()
    plugin._device = device
    plugin._os_id = "bazzite"
    plugin._tdp_backend = backend
    assert plugin._recover_tdp_runtime_transaction() is False

    attributes = (
        tmp_path
        / "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes"
    )
    for name in ("ppt_pl1_spl",):
        path = attributes / name
        path.mkdir(parents=True)
        (path / "current_value").write_text("30", encoding="utf-8")
        (path / "min_value").write_text("5", encoding="utf-8")
        (path / "max_value").write_text("35", encoding="utf-8")

    first_state = asyncio.run(plugin.get_tdp_state())
    assert first_state["supported"] is False
    assert first_state["recovery_pending"] is True
    assert lock_path.exists()
    assert (attributes / "ppt_pl1_spl/current_value").read_text() == "30"

    for name in ("ppt_pl2_sppt", "ppt_pl3_fppt"):
        path = attributes / name
        path.mkdir(parents=True)
        (path / "current_value").write_text("30", encoding="utf-8")
        (path / "min_value").write_text("5", encoding="utf-8")
        (path / "max_value").write_text("35", encoding="utf-8")

    second_state = asyncio.run(plugin.get_tdp_state())
    assert second_state["supported"] is False
    assert second_state["recovery_pending"] is True
    assert lock_path.exists()
    for name in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        assert (attributes / name / "current_value").read_text() == "30"

    profile_dir = (
        tmp_path
        / "sys/class/platform-profile/platform-profile-0"
    )
    profile_dir.mkdir(parents=True)
    (profile_dir / "name").write_text(
        "lenovo-wmi-gamezone",
        encoding="utf-8",
    )
    (profile_dir / "profile").write_text("performance", encoding="utf-8")

    async def recover():
        state = await plugin.get_tdp_state()
        guard_started = plugin._tdp_guard_task is not None
        plugin._stop_tdp_guard_loop()
        return state, guard_started

    state, guard_started = asyncio.run(recover())

    assert state["supported"] is True
    assert state["backend"] == "firmware-attr:lenovo-wmi-other"
    assert state["recovery_pending"] is False
    assert guard_started is True
    assert not lock_path.exists()
    assert (attributes / "ppt_pl1_spl/current_value").read_text() == "12\n"
    assert (attributes / "ppt_pl2_sppt/current_value").read_text() == "18\n"
    assert (attributes / "ppt_pl3_fppt/current_value").read_text() == "24\n"
    assert (profile_dir / "profile").read_text() == "balanced\n"


@pytest.fixture
def fake_hhd(monkeypatch):
    import main as main_mod
    fh = FakeHHD()
    monkeypatch.setattr(main_mod.controller_hhd, "current_tdp_enable", fh.current_tdp_enable)
    monkeypatch.setattr(main_mod.controller_hhd, "set_tdp_enable", fh.set_tdp_enable)
    return fh


# ---------------------------------------------------------------------------
# Conflict readout
# ---------------------------------------------------------------------------

def test_conflict_reports_hhd_managing(Plugin, fake_hhd):
    import main as main_mod
    p = Plugin()
    p._init()
    p._controller_backend.manager = main_mod.controller_detect.HHD
    fake_hhd.set(True)
    out = asyncio.run(p.get_tdp_conflict())
    assert out == {
        "hhd_present": True,
        "hhd_managing": True,
        "powerstation_active": False,
    }


def _anatase_plugin(Plugin, monkeypatch):
    import main as main_mod

    monkeypatch.setattr(main_mod.osinfo, "read_os_id", lambda: "anatase")
    monkeypatch.setattr(main_mod.osinfo, "read_os_name", lambda: "Anatase")
    plugin = Plugin()
    plugin._init()
    return plugin, main_mod


def test_anatase_selects_isolated_hhd_power_client_and_reports_platform(
    Plugin,
    monkeypatch,
):
    from pdc_platform import anatase_hhd

    plugin, _main_mod = _anatase_plugin(Plugin, monkeypatch)

    assert plugin._hhd_tdp_client is anatase_hhd
    assert plugin._report_environment()["platform"] == {
        "id": "anatase",
        "support_tier": "first-class",
    }


def test_anatase_blocks_tdp_until_hhd_ownership_is_known(Plugin, monkeypatch):
    plugin, _main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._tdp_backend.set_levels_calls = 0

    result = plugin._reapply_tdp()

    assert result.ok is False
    assert result.detail == "tdp-ownership-unconfirmed"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_anatase_hhd_owner_blocks_tdp_writes(Plugin, monkeypatch):
    plugin, main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._controller_backend.manager = main_mod.controller_detect.HHD
    plugin._hhd_tdp_client = FakeHHD(True)

    asyncio.run(plugin._prime_tdp_ownership())
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._reapply_tdp()

    assert plugin._tdp_external_owner is True
    assert result.detail == "tdp-ownership-unconfirmed"
    assert plugin._tdp_backend.set_levels_calls == 0


def test_anatase_without_hhd_allows_direct_backend(Plugin, monkeypatch):
    plugin, _main_mod = _anatase_plugin(Plugin, monkeypatch)

    asyncio.run(plugin._prime_tdp_ownership())
    plugin._tdp_backend.set_levels_calls = 0
    result = plugin._reapply_tdp()

    assert plugin._tdp_external_owner is False
    assert result.ok is True
    assert plugin._tdp_backend.set_levels_calls == 1


def test_anatase_startup_relinquishes_stale_ownership_without_recovery_write(
    Plugin,
    monkeypatch,
):
    plugin, main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._controller_backend.manager = main_mod.controller_detect.HHD
    plugin._hhd_tdp_client = FakeHHD(True)
    events = []
    backend = types.SimpleNamespace(
        safety_locked=True,
        recover_runtime_transaction=lambda: events.append("recover")
        or {"ok": True, "detail": "recovered"},
    )

    def relinquish():
        events.append("relinquish")
        backend.safety_locked = False
        return {"ok": True, "detail": "stale ownership relinquished"}

    backend.relinquish_ownership = relinquish
    plugin._tdp_backend = backend

    async def direct(fn):
        return fn()

    plugin._offload_call = direct

    assert asyncio.run(plugin._recover_tdp_startup_state()) is True
    assert plugin._tdp_external_owner is True
    assert events == ["relinquish"]


def test_anatase_startup_keeps_recovery_locked_when_hhd_is_unreadable(
    Plugin,
    monkeypatch,
):
    plugin, main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._controller_backend.manager = main_mod.controller_detect.HHD
    plugin._hhd_tdp_client = FakeHHD(None)
    events = []
    plugin._tdp_backend = types.SimpleNamespace(
        safety_locked=True,
        relinquish_ownership=lambda: events.append("relinquish"),
        recover_runtime_transaction=lambda: events.append("recover"),
    )

    async def direct(fn):
        return fn()

    plugin._offload_call = direct

    assert asyncio.run(plugin._recover_tdp_startup_state()) is False
    assert plugin._tdp_external_owner is True
    assert events == []


def test_anatase_startup_recovers_when_hhd_confirms_disabled(
    Plugin,
    monkeypatch,
):
    plugin, main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._controller_backend.manager = main_mod.controller_detect.HHD
    plugin._hhd_tdp_client = FakeHHD(False)
    events = []
    plugin._tdp_backend = types.SimpleNamespace(
        safety_locked=True,
        recover_runtime_transaction=lambda: events.append("recover")
        or {"ok": True, "detail": "recovered"},
    )

    async def direct(fn):
        return fn()

    plugin._offload_call = direct

    assert asyncio.run(plugin._recover_tdp_startup_state()) is True
    assert plugin._tdp_external_owner is False
    assert events == ["recover"]


def test_non_anatase_startup_preserves_runtime_recovery(Plugin):
    plugin = Plugin()
    plugin._init()
    plugin._os_id = "bazzite"
    events = []
    plugin._tdp_backend = types.SimpleNamespace(
        safety_locked=True,
        recover_runtime_transaction=lambda: events.append("recover")
        or {"ok": True, "detail": "recovered"},
    )

    async def direct(fn):
        return fn()

    plugin._offload_call = direct

    assert asyncio.run(plugin._recover_tdp_startup_state()) is True
    assert events == ["recover"]


def test_anatase_takeover_unlocks_tdp_only_after_hhd_confirms(
    Plugin,
    monkeypatch,
):
    plugin, main_mod = _anatase_plugin(Plugin, monkeypatch)
    plugin._controller_backend.manager = main_mod.controller_detect.HHD
    hhd = FakeHHD(True)
    plugin._hhd_tdp_client = hhd
    asyncio.run(plugin._prime_tdp_ownership())
    plugin._tdp_backend.set_levels_calls = 0

    result = asyncio.run(plugin.take_tdp_control())

    assert result == {"ok": True, "hhd_managing": False}
    assert plugin._tdp_external_owner is False
    assert hhd.value is False
    assert plugin._tdp_backend.set_levels_calls == 1


def test_conflict_no_hhd_present(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    # Default test backend manager is NONE → we never poke HHD's API.
    out = asyncio.run(p.get_tdp_conflict())
    assert out["hhd_present"] is False
    assert out["hhd_managing"] is False


def test_conflict_reports_active_powerstation_tdp_interface(Plugin):
    p = Plugin()
    p._init()
    p._powerstation_detector.tdp_active = lambda: True

    out = asyncio.run(p.get_tdp_conflict())

    assert out["powerstation_active"] is True


# ---------------------------------------------------------------------------
# Take / release control (reversible, saves previous value)
# ---------------------------------------------------------------------------

def test_take_and_restore_hands_hhd_back(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    out = asyncio.run(p.take_tdp_control())
    assert out["ok"] is True
    assert fake_hhd.value is False                 # HHD's TDP handed to us
    assert p._settings["hhd_tdp_prev"] is True     # remembered for restore
    p._restore_hhd_tdp()
    assert fake_hhd.value is True                  # restored
    assert p._settings["hhd_tdp_prev"] is None


def test_take_never_disables_hhd_when_deferred_backend_probe_fails(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    probes = []
    p._tdp_backend.probe = lambda: probes.append(True) or False
    fake_hhd.set(True)

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is True
    assert fake_hhd.value is True
    assert p._settings["hhd_tdp_prev"] is None
    assert probes == [True]


def test_take_restores_hhd_immediately_when_first_panel_apply_fails(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)

    async def failed_apply(_reason):
        return TdpResult(20, None, False, "probe lost")

    p._apply_tdp_now = failed_apply

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is True
    assert fake_hhd.value is True
    assert p._settings["hhd_tdp_prev"] is None


def test_failed_take_keeps_hhd_off_until_backend_release_succeeds(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    p._tdp_backend.release_ok = False
    fake_hhd.set(True)

    async def failed_apply(_reason):
        return TdpResult(20, None, False, "firmware transaction pending")

    p._apply_tdp_now = failed_apply

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is False
    assert "hardware restore pending" in out["detail"]
    assert fake_hhd.value is False
    assert p._settings["hhd_tdp_prev"] is True
    assert p._tdp_backend.release_calls == 1


def test_failed_apply_reports_hhd_restored_from_an_existing_marker(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    p._settings["hhd_tdp_prev"] = True
    fake_hhd.set(False)

    async def failed_apply(_reason):
        return TdpResult(20, None, False, "probe lost")

    p._apply_tdp_now = failed_apply

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is True
    assert fake_hhd.value is True
    assert p._settings["hhd_tdp_prev"] is None


def test_failed_marker_clear_keeps_recovery_marker_and_reports_hhd_active(
    Plugin,
    fake_hhd,
):
    p = Plugin()
    p._init()
    p._settings["hhd_tdp_prev"] = True
    fake_hhd.set(False)
    p._save = lambda: (_ for _ in ()).throw(OSError("disk full"))

    async def failed_apply(_reason):
        return TdpResult(20, None, False, "probe lost")

    p._apply_tdp_now = failed_apply

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is True
    assert "marker clear pending" in out["detail"]
    assert fake_hhd.value is True
    assert p._settings["hhd_tdp_prev"] is True


def test_failed_hhd_restore_reports_last_confirmed_owner_without_guessing(
    Plugin,
    fake_hhd,
    monkeypatch,
):
    import main as main_mod

    p = Plugin()
    p._init()
    fake_hhd.set(True)
    responses = iter((False, None))

    def set_tdp_enable(enabled):
        response = next(responses)
        if response is not None:
            fake_hhd.set(response)
        return response

    monkeypatch.setattr(main_mod.controller_hhd, "set_tdp_enable", set_tdp_enable)

    async def failed_apply(_reason):
        return TdpResult(20, None, False, "probe lost")

    p._apply_tdp_now = failed_apply

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is False
    assert "HHD restore pending" in out["detail"]
    assert fake_hhd.value is False
    assert p._settings["hhd_tdp_prev"] is True


def test_take_blocked_by_desktop_migration_reports_live_hhd_owner(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    p._desktop_recognition_migration_pending = True
    p._desktop_recognition_migration_last_attempt = 0.0
    p._desktop_power.restore = lambda: {
        "ok": False,
        "detail": "surface unavailable",
    }
    fake_hhd.set(True)

    out = asyncio.run(p.take_tdp_control())

    assert out["ok"] is False
    assert out["hhd_managing"] is True
    assert out["detail"] == "desktop migration pending"


def test_take_when_hhd_unreachable_is_honest(Plugin, monkeypatch):
    import main as main_mod
    monkeypatch.setattr(main_mod.controller_hhd, "current_tdp_enable",
                        lambda root="/": None)
    p = Plugin()
    p._init()
    out = asyncio.run(p.take_tdp_control())
    assert out["ok"] is False
    assert p._settings["hhd_tdp_prev"] is None


def test_take_does_not_overwrite_saved_prev(Plugin, fake_hhd):
    # Already off (someone else) → don't record False as the value to restore to.
    p = Plugin()
    p._init()
    p._settings["hhd_tdp_prev"] = True   # a prior take is already remembered
    fake_hhd.set(False)
    asyncio.run(p.take_tdp_control())
    assert p._settings["hhd_tdp_prev"] is True   # unchanged


def test_take_does_not_apply_when_hhd_refuses_to_release(Plugin, monkeypatch):
    import main as main_mod

    p = Plugin()
    p._init()
    monkeypatch.setattr(main_mod.controller_hhd, "current_tdp_enable", lambda: True)
    monkeypatch.setattr(
        main_mod.controller_hhd,
        "set_tdp_enable",
        lambda enabled: True,
    )
    before = p._tdp_backend.set_levels_calls

    out = asyncio.run(p.take_tdp_control())

    assert out == {"ok": False, "hhd_managing": True}
    assert p._settings["hhd_tdp_prev"] is True
    assert p._tdp_backend.set_levels_calls == before


def test_take_retries_marker_persistence_before_disabling_hhd(
    Plugin, fake_hhd, monkeypatch
):
    p = Plugin()
    p._init()
    real_save = p._save
    saves = 0

    def fail_first_save():
        nonlocal saves
        saves += 1
        if saves == 1:
            raise OSError("disk full")
        return real_save()

    monkeypatch.setattr(p, "_save", fail_first_save)
    before = p._tdp_backend.set_levels_calls

    first = asyncio.run(p.take_tdp_control())

    assert first == {"ok": False, "hhd_managing": True}
    assert fake_hhd.value is True
    assert p._settings["hhd_tdp_prev"] is None
    assert p._tdp_backend.set_levels_calls == before

    second = asyncio.run(p.take_tdp_control())

    assert second == {"ok": True, "hhd_managing": False}
    assert fake_hhd.value is False
    assert p._settings["hhd_tdp_prev"] is True


def test_restore_noop_when_never_taken(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    p._restore_hhd_tdp()
    assert fake_hhd.value is True          # untouched — nothing to restore
    assert p._settings["hhd_tdp_prev"] is None


def test_power_handoff_releases_backend_before_external_owners(Plugin):
    plugin = Plugin()
    plugin._init()
    events = []
    plugin._tdp_backend.release = lambda: events.append("backend") or True
    plugin._restore_steamdeck_ppt = lambda preserve_ownership=False: (
        events.append("steamdeck") or True
    )
    plugin._restore_hhd_tdp = lambda preserve_ownership=False: (
        events.append("hhd") or True
    )

    assert plugin._restore_power_handoff() is True
    assert events == ["backend", "steamdeck", "hhd"]


def test_power_handoff_stops_before_hhd_if_backend_restore_fails(Plugin):
    plugin = Plugin()
    plugin._init()
    external = []
    plugin._tdp_backend.release_ok = False
    plugin._restore_steamdeck_ppt = lambda preserve_ownership=False: (
        external.append("steamdeck") or True
    )
    plugin._restore_hhd_tdp = lambda preserve_ownership=False: (
        external.append("hhd") or True
    )

    assert plugin._restore_power_handoff() is False
    assert plugin._tdp_backend.release_calls == 1
    assert external == []


# ---------------------------------------------------------------------------
# Master switch gating
# ---------------------------------------------------------------------------

def test_reapply_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    res = p._reapply_tdp()
    assert p._tdp_backend.set_levels_calls == 0
    assert res.ok is True
    assert res.detail == "tdp-control-disabled"


def test_reapply_writes_when_control_enabled(Plugin):
    p = Plugin()
    p._init()
    p._tdp_backend.set_levels_calls = 0
    p._reapply_tdp()
    assert p._tdp_backend.set_levels_calls == 1


def test_set_tdp_watts_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    out = asyncio.run(p.set_tdp_watts(20, "global"))
    assert out["ok"] is False
    assert p._tdp_backend.set_levels_calls == 0


def test_stale_game_tdp_rpc_cannot_retarget_active_game(Plugin):
    p = Plugin()
    p._init()
    p._set_current_appid("game-b")
    before = p._tdp_backend.set_levels_calls

    result = asyncio.run(
        p.set_tdp_watts(20, "game", "game-a", "game-a")
    )

    assert result["ok"] is False
    assert result["detail"] == "stale-context"
    assert p._current_appid == "game-b"
    assert p._tdp_backend.set_levels_calls == before
    assert p._tdp_profiles.has_game("game-a") is False


def test_set_tdp_levels_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    out = asyncio.run(p.set_tdp_levels(5, 10, "global"))
    assert out["ok"] is False
    assert p._tdp_backend.set_levels_calls == 0


def test_set_auto_tdp_noop_when_control_disabled(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    asyncio.run(p.set_auto_tdp(True, "global"))
    assert p._tdp_backend.set_levels_calls == 0


# ---------------------------------------------------------------------------
# Master-switch RPC: OFF restores HHD, ON re-applies our setpoint
# ---------------------------------------------------------------------------

def test_set_control_enabled_off_restores_hhd(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    asyncio.run(p.take_tdp_control())
    assert fake_hhd.value is False
    assert asyncio.run(p.set_tdp_control_enabled(False)) is False
    assert fake_hhd.value is True                 # handed back on release
    assert p._settings["tdp_control_enabled"] is False


def test_set_control_enabled_off_invalidates_queued_write(Plugin):
    p = Plugin()
    p._init()
    queued = p._capture_tdp_command("queued")
    asyncio.run(p.set_tdp_control_enabled(False))
    p._tdp_backend.set_levels_calls = 0
    result = p._execute_tdp_command(queued)
    assert result.detail == "stale-generation"
    assert p._tdp_backend.set_levels_calls == 0


def test_set_control_enabled_on_reapplies(Plugin):
    p = Plugin()
    p._init()
    p._settings["tdp_control_enabled"] = False
    p._tdp_backend.set_levels_calls = 0
    assert asyncio.run(p.set_tdp_control_enabled(True)) is True
    assert p._tdp_backend.set_levels_calls == 1


def test_get_control_enabled_default_true(Plugin):
    p = Plugin()
    assert asyncio.run(p.get_tdp_control_enabled()) is True


# ---------------------------------------------------------------------------
# Persisted "seen" flags (durable across reboot; CEF localStorage is not)
# ---------------------------------------------------------------------------

def test_seen_flag_setters_persist(Plugin):
    p = Plugin()
    p._init()
    assert asyncio.run(p.set_seen_autotdp_notice(True)) is True
    assert asyncio.run(p.set_seen_tdp_conflict_takeover(True)) is True
    assert p._settings["seen_autotdp_notice"] is True
    assert p._settings["seen_tdp_conflict_takeover"] is True
    # a fresh instance reading the same store sees them
    p2 = Plugin()
    p2._init()
    assert p2._settings["seen_autotdp_notice"] is True
    assert p2._settings["seen_tdp_conflict_takeover"] is True


def test_tdp_state_exposes_control_and_seen_flags(Plugin):
    p = Plugin()
    p._init()
    st = asyncio.run(p.get_tdp_state())
    # Defaults: control on, notices unseen.
    assert st["tdp_control_enabled"] is True
    assert st["seen_autotdp_notice"] is False
    assert st["seen_tdp_conflict_takeover"] is False
    # They track the persisted settings.
    p._settings["tdp_control_enabled"] = False
    p._settings["seen_autotdp_notice"] = True
    p._settings["seen_tdp_conflict_takeover"] = True
    st = asyncio.run(p.get_tdp_state())
    assert st["tdp_control_enabled"] is False
    assert st["seen_autotdp_notice"] is True
    assert st["seen_tdp_conflict_takeover"] is True


# ---------------------------------------------------------------------------
# Lifecycle restore: hand HHD back
# ---------------------------------------------------------------------------

def test_unload_restores_hhd(Plugin, fake_hhd):
    p = Plugin()
    p._init()
    fake_hhd.set(True)
    asyncio.run(p.take_tdp_control())
    assert fake_hhd.value is False
    asyncio.run(p._unload())
    assert fake_hhd.value is True
