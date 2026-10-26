import asyncio
import copy
from types import SimpleNamespace

import pytest

from test_tdp_control_rpc import Plugin  # noqa: F401
from device_profiles import DEVICE_TABLE


def owned_plugin(Plugin):
    plugin = Plugin()
    plugin._init()
    plugin._device = next(p for p in DEVICE_TABLE if p.key == "steam_deck_oled")
    plugin._tdp_backend.name = "steamdeck-hwmon"
    plugin._gpu_clock.backend = "amdgpu"
    plugin._gpu_clock.supported = True
    plugin._tdp_backend.capture_ppt = lambda: None
    plugin._set_current_appid("42")
    plugin._power_ownership.observe("42", "active")
    return plugin


def test_steam_observation_precedes_context_reapply(Plugin, monkeypatch):
    plugin = owned_plugin(Plugin)
    seen = []
    monkeypatch.setattr(plugin, "_reapply_all", lambda **kw: seen.append(plugin._game_power_write_allowed()))
    asyncio.run(plugin.set_current_game("42", "Game", "active"))
    assert seen == [False]
    assert plugin._game_power_owner_state()["owner"] == "steam"


@pytest.mark.parametrize("operation", ["watts", "preset", "levels", "boost", "auto"])
def test_global_power_save_does_not_write_or_change_eco_firmware(Plugin, operation):
    plugin = owned_plugin(Plugin)
    plugin._settings["eco_enabled"] = True
    plugin._settings["firmware_mode"] = "balanced"
    before = plugin._tdp_backend.set_levels_calls
    operations = {
        "watts": lambda: plugin.set_tdp_watts(20, "global", None, "42"),
        "preset": lambda: plugin.apply_power_preset(20, "global", None, None, "42"),
        "levels": lambda: plugin.set_tdp_levels(2, 3, "global", None, "42"),
        "boost": lambda: plugin.set_tdp_boost_mode("auto", "global", None, "42"),
        "auto": lambda: plugin.set_auto_tdp(True, "global", None, "42"),
    }
    asyncio.run(operations[operation]())
    assert plugin._tdp_backend.set_levels_calls == before
    assert plugin._settings["eco_enabled"] is True
    assert plugin._settings["firmware_mode"] == "balanced"
    profile = plugin._tdp_profiles.effective(None)
    if operation in ("watts", "preset"):
        assert profile["pl1"] == 20
    if operation == "levels":
        assert profile["pl2"] == 12
    if operation == "boost":
        assert profile["mode"] == "auto"


def test_game_edit_requires_explicit_claim_and_guard_stays_idle(Plugin):
    plugin = owned_plugin(Plugin)
    before = plugin._tdp_backend.set_levels_calls
    result = asyncio.run(plugin.set_tdp_watts(20, "game", "42", "42"))
    assert result["ok"] is False
    assert not plugin._tdp_profiles.has_game("42")
    plugin._tdp_guard_tick()
    plugin._reapply_tdp()
    assert plugin._tdp_backend.set_levels_calls == before
    assert plugin._auto_control_active() is False


def test_owner_rpc_does_not_claim_without_safe_baseline(Plugin):
    plugin = owned_plugin(Plugin)
    state = asyncio.run(plugin.get_game_power_owner())
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is False
    assert result["detail"] == "baseline-required"
    assert result["owner"] == "steam"
    stale = asyncio.run(plugin.set_game_power_owner("43", "steam", state["revision"]))
    assert stale["ok"] is False


def test_legacy_context_retains_write_permission(Plugin):
    plugin = Plugin()
    plugin._init()
    plugin._set_current_appid("42")
    result = asyncio.run(plugin.set_tdp_watts(20, "global"))
    assert result["ok"] is True
    assert plugin._tdp_backend.set_levels_calls > 0


def test_gpu_global_saves_without_manual_or_auto_writes(Plugin, monkeypatch):
    plugin = owned_plugin(Plugin)
    writes = []
    monkeypatch.setattr(plugin._gpu_clock, "set", lambda *args: writes.append(args))
    monkeypatch.setattr(plugin._gpu_clock, "set_auto", lambda: writes.append("auto"))
    asyncio.run(plugin.set_gpu_clock(500, 900, "global", None, "42"))
    assert plugin._gpu_profiles.clock(None) == {"manual": True, "min": 500, "max": 900}
    plugin._apply_gpu_clock()
    plugin._run_gpu_clock({"mode": "manual", "min_mhz": 500, "max_mhz": 900})
    asyncio.run(plugin.set_gpu_clock_auto("global", None, "42"))
    assert plugin._gpu_profiles.clock(None)["manual"] is False
    assert writes == []


def test_unknown_observation_blocks_but_does_not_change_other_scoped_features(Plugin):
    plugin = owned_plugin(Plugin)
    plugin._power_ownership.observe("42", "unknown")
    assert plugin._game_power_write_allowed() is False
    assert plugin._resolve_scope("game", "42") == "game"


def test_explicit_return_to_steam_invalidates_workers_and_persists(Plugin):
    plugin = owned_plugin(Plugin)
    state = plugin._power_ownership.state()
    plugin._power_ownership.set_owner("42", "pdc", state["revision"])
    before_tdp, before_gpu = plugin._tdp_generation, plugin._gpu_generation
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner("42", "steam", state["revision"]))
    assert result["ok"] is True
    assert result["write_allowed"] is False
    assert plugin._tdp_generation > before_tdp
    assert plugin._gpu_generation > before_gpu


def deck_owned_plugin(Plugin, monkeypatch):
    plugin = owned_plugin(Plugin)
    plugin._device = next(p for p in DEVICE_TABLE if p.key == "steam_deck_oled")
    plugin._tdp_backend.name = "steamdeck-hwmon"
    monkeypatch.setattr(plugin._tdp_backend, "capture_ppt", lambda: {"slow": 12, "fast": 15}, raising=False)
    monkeypatch.setattr(plugin._gpu_clock, "backend", "amdgpu", raising=False)
    monkeypatch.setattr(plugin._gpu_clock, "supported", True)
    monkeypatch.setattr(plugin._gpu_clock, "capture_state", lambda: {"level": "manual", "window": (500, 900)})
    return plugin


@pytest.mark.parametrize("owner", ["steam", "pdc", None, "inferred_steam"])
def test_native_reset_preserves_owner_and_seeds_live_baseline(Plugin, monkeypatch, owner):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    if owner is None:
        plugin._power_ownership.observe("42", "inactive")
    elif owner != "inferred_steam":
        plugin._power_ownership.set_owner("42", owner, plugin._power_ownership.state()["revision"])
    globals_before = [copy.deepcopy(s._data["global"]) for s in (plugin._tdp_profiles, plugin._gpu_profiles)]

    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        assert begun["ok"] and begun["reset_pending"]
        assert not plugin._game_power_write_allowed()
        rejected = await plugin.set_game_power_owner("42", "pdc", begun["revision"])
        assert rejected["detail"] == "reset_in_progress"
        return await plugin.finish_game_power_reset(begun["token"], {"appFrameRate": 60})

    result = asyncio.run(run())
    assert result["ok"] and not result["reset_pending"]
    assert result["explicit_owner"] == (None if owner == "inferred_steam" else owner)
    if owner in ("steam", "inferred_steam"):
        assert not plugin._tdp_profiles.has_game("42")
        assert not plugin._gpu_profiles.has_game("42")
    else:
        assert plugin._tdp_profiles.effective("42")["pl1"] == 12
        assert plugin._gpu_profiles.clock("42")["min"] == 500
    assert result["steam_settings"] == ({"appFrameRate": 60} if owner == "pdc" else {})
    assert globals_before == [s._data["global"] for s in (plugin._tdp_profiles, plugin._gpu_profiles)]


@pytest.mark.parametrize("operation", ["abort", "timeout", "readback_exception"])
def test_native_reset_cancellation_restores_intent_and_is_idempotent(Plugin, monkeypatch, operation):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._power_ownership.set_owner("42", "pdc", plugin._power_ownership.state()["revision"], {"appFrameRate": 40})
    reapplied = []
    async def apply(reason):
        reapplied.append("tdp")
        return SimpleNamespace(ok=True)
    monkeypatch.setattr(plugin, "_apply_tdp_now", apply)
    def apply_gpu(*args, **kwargs):
        reapplied.append("gpu")
        return {"ok": True}
    monkeypatch.setattr(plugin, "_run_gpu_clock", apply_gpu)
    monkeypatch.setattr(plugin, "_record_gpu_clock_transition", lambda *args: None)
    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        blocked = await plugin.update_game_steam_setting("42", begun["revision"], "appFrameRate", 60)
        assert blocked["detail"] == "reset_in_progress"
        if operation == "timeout":
            await plugin._expire_game_power_reset(begun["token"])
        elif operation == "readback_exception":
            def fail():
                raise RuntimeError("capture failed")
            monkeypatch.setattr(plugin, "_capture_game_power_baseline", fail)
            assert not (await plugin.finish_game_power_reset(begun["token"], {}))["ok"]
        else:
            await plugin.abort_game_power_reset(begun["token"])
        await plugin.abort_game_power_reset(begun["token"])
    asyncio.run(run())
    assert reapplied == ["tdp", "gpu"]
    assert plugin._game_power_write_allowed()
    assert plugin._power_ownership.state()["steam_settings"] == {"appFrameRate": 40}


@pytest.mark.parametrize("failure", ["tdp", "gpu"])
def test_native_reset_abort_reports_rejected_restore(Plugin, monkeypatch, failure):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._power_ownership.set_owner("42", "pdc", plugin._power_ownership.state()["revision"])
    async def apply(reason):
        return SimpleNamespace(ok=failure != "tdp")
    monkeypatch.setattr(plugin, "_apply_tdp_now", apply)
    monkeypatch.setattr(plugin, "_run_gpu_clock", lambda *args, **kwargs: {"ok": failure != "gpu"})
    monkeypatch.setattr(plugin, "_record_gpu_clock_transition", lambda *args: None)
    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        result = await plugin.abort_game_power_reset(begun["token"])
        assert result["ok"] is False
        assert result["detail"] == "reset_restore_failed"
        assert not result["reset_pending"]
    asyncio.run(run())


def test_native_reset_old_token_cannot_write_new_context(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)

    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        plugin._set_current_appid("43")
        result = await plugin.finish_game_power_reset(begun["token"], {})
        assert not result["ok"]
        assert not plugin._tdp_profiles.has_game("42")
        assert not result["reset_pending"]
    asyncio.run(run())


@pytest.mark.parametrize("fail_save", [False, True])
def test_native_global_reset_captures_baseline_without_game_profile(Plugin, monkeypatch, fail_save):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._set_current_appid(None)
    plugin._power_ownership.observe(None, "inactive")
    monkeypatch.setattr(plugin._gpu_clock, "capture_state", lambda: {"level": "auto", "window": (200, 1600)})
    previous = [copy.deepcopy(s._data) for s in (plugin._tdp_profiles, plugin._gpu_profiles)]
    if fail_save:
        def fail():
            raise OSError("disk failure")
        monkeypatch.setattr(plugin._gpu_profiles, "_save", fail)
    async def run():
        begun = await plugin.begin_game_power_reset(None, plugin._power_ownership.state()["revision"])
        assert begun["ok"]
        return await plugin.finish_game_power_reset(begun["token"], {})
    result = asyncio.run(run())
    assert result["ok"] is not fail_save
    assert result["explicit_owner"] is None
    assert result["steam_settings"] == {}
    if fail_save:
        assert previous == [s._data for s in (plugin._tdp_profiles, plugin._gpu_profiles)]
    else:
        assert plugin._tdp_profiles.effective(None)["pl1"] == 12
        assert plugin._gpu_profiles.clock(None) == {"manual": False, "min": None, "max": None}
        assert plugin._tdp_profiles._data.get("games", {}) == previous[0].get("games", {})


def test_native_global_reset_rejected_while_game_active(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    result = asyncio.run(plugin.begin_game_power_reset(None, plugin._power_ownership.state()["revision"]))
    assert not result["ok"] and result["detail"] == "stale_context"


@pytest.mark.parametrize("interruption", ["deadline", "context"])
def test_native_reset_revalidates_after_capture(Plugin, monkeypatch, interruption):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    capture = plugin._capture_game_power_baseline
    def interrupted_capture():
        value = capture()
        if interruption == "context":
            plugin._set_current_appid("43")
        else:
            plugin._game_power_reset["deadline"] = 0
        return value
    monkeypatch.setattr(plugin, "_capture_game_power_baseline", interrupted_capture)
    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        result = await plugin.finish_game_power_reset(begun["token"], {})
        assert not result["ok"] and not result["reset_pending"]
        assert not plugin._tdp_profiles.has_game("42")
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["tdp", "gpu", "owner", "readback"])
def test_native_reset_failure_rolls_back_and_releases_gate(Plugin, monkeypatch, failure):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._power_ownership.set_owner("42", "pdc", plugin._power_ownership.state()["revision"])
    previous = [copy.deepcopy(s._data) for s in (plugin._tdp_profiles, plugin._gpu_profiles)]
    if failure == "readback":
        monkeypatch.setattr(plugin, "_capture_game_power_baseline", lambda: None)
    else:
        store = {"tdp": plugin._tdp_profiles, "gpu": plugin._gpu_profiles, "owner": plugin._power_ownership}[failure]
        def fail(*args, **kwargs):
            raise OSError("disk failure")
        monkeypatch.setattr(store, "set_owner" if failure == "owner" else "_save", fail)

    async def run():
        begun = await plugin.begin_game_power_reset("42", plugin._power_ownership.state()["revision"])
        return await plugin.finish_game_power_reset(begun["token"], {"appFrameRate": 60})
    result = asyncio.run(run())
    assert not result["ok"] and not result["reset_pending"]
    assert result["explicit_owner"] == "pdc"
    assert previous == [s._data for s in (plugin._tdp_profiles, plugin._gpu_profiles)]


def test_deck_claim_seeds_live_game_baseline_without_hardware_or_global_change(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    writes = []
    monkeypatch.setattr(plugin._gpu_clock, "set", lambda *args: writes.append(args))
    monkeypatch.setattr(plugin._gpu_clock, "set_auto", lambda: writes.append("auto"))
    plugin._tdp_profiles.set_auto_tdp("game", True, "42")
    global_tdp = copy.deepcopy(plugin._tdp_profiles._data["global"])
    global_gpu = copy.deepcopy(plugin._gpu_profiles._data["global"])
    before = plugin._tdp_backend.set_levels_calls
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is True
    assert result["owner"] == "pdc"
    assert plugin._tdp_profiles.effective("42")["pl2"] == 12
    assert plugin._tdp_profiles.effective("42")["pl3"] == 15
    assert plugin._tdp_profiles.auto_tdp("42") is False
    assert plugin._gpu_profiles.clock("42") == {"manual": True, "min": 500, "max": 900}
    assert plugin._tdp_profiles._data["global"] == global_tdp
    assert plugin._gpu_profiles._data["global"] == global_gpu
    assert plugin._tdp_backend.set_levels_calls == before
    assert writes == []


@pytest.mark.parametrize("failed_store", ["tdp", "gpu", "owner"])
def test_claim_persistence_failure_never_grants_ownership(Plugin, monkeypatch, failed_store):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    previous_tdp = copy.deepcopy(plugin._tdp_profiles._data)
    previous_gpu = copy.deepcopy(plugin._gpu_profiles._data)

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    target = {"tdp": plugin._tdp_profiles, "gpu": plugin._gpu_profiles,
              "owner": plugin._power_ownership}[failed_store]
    monkeypatch.setattr(target, "set_owner" if failed_store == "owner" else "_save", fail)
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is False
    assert result["owner"] == "steam"
    assert result["rollback_ok"] is (failed_store == "owner")
    assert plugin._tdp_profiles._data == previous_tdp
    assert plugin._gpu_profiles._data == previous_gpu
    assert plugin._tdp_backend.set_levels_calls == 0


@pytest.mark.parametrize("level", [None, "high", "profile_peak"])
def test_claim_rejects_unrepresentable_gpu_mode(Plugin, monkeypatch, level):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    monkeypatch.setattr(plugin._gpu_clock, "capture_state", lambda: {"level": level, "window": (500, 900)})
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is False
    assert result["owner"] == "steam"
    assert not plugin._tdp_profiles.has_game("42")


def test_claim_and_update_native_intent_with_revision(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner(
        "42", "pdc", state["revision"], {"appFrameRate": 40, "allowTearing": False}
    ))
    assert result["ok"] is True
    assert result["steam_settings"]["appFrameRate"] == 40
    updated = asyncio.run(plugin.update_game_steam_setting(
        "42", result["revision"], "appFrameRate", 60
    ))
    assert updated["ok"] is True
    assert updated["steam_settings"]["appFrameRate"] == 60
    rejected = asyncio.run(plugin.update_game_steam_setting(
        "42", result["revision"], "appFrameRate", 30
    ))
    assert rejected["ok"] is False
    assert rejected["steam_settings"]["appFrameRate"] == 60
    assert plugin._tdp_backend.set_levels_calls == 0


def test_invalid_native_snapshot_does_not_seed_profiles(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner(
        "42", "pdc", state["revision"], {"unknown": True}
    ))
    assert result["ok"] is False
    assert not plugin._tdp_profiles.has_game("42")
    assert not plugin._gpu_profiles.has_game("42")


def test_context_change_during_baseline_capture_cannot_claim_previous_game(Plugin, monkeypatch):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    capture = plugin._capture_game_power_baseline

    def changed_context():
        baseline = capture()
        plugin._set_current_appid("43")
        return baseline

    monkeypatch.setattr(plugin, "_capture_game_power_baseline", changed_context)
    state = plugin._power_ownership.state()
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is False
    assert result["context_appid"] == "43"
    assert not plugin._tdp_profiles.has_game("42")
    assert not plugin._gpu_profiles.has_game("42")


def test_non_deck_observation_keeps_legacy_and_refuses_unsupported_claim(Plugin, monkeypatch):
    plugin = Plugin()
    plugin._init()
    plugin._device = next(p for p in DEVICE_TABLE if p.key == "rog_ally")
    monkeypatch.setattr(plugin, "_reapply_all", lambda **kw: None)
    asyncio.run(plugin.set_current_game("42", "Game", "active"))
    state = plugin._game_power_owner_state()
    assert state["supported"] is False
    assert state["write_allowed"] is True
    assert state["reason"] == "unsupported_ownership"
    assert state["observed"] is False
    result = asyncio.run(plugin.set_game_power_owner("42", "pdc", state["revision"]))
    assert result["ok"] is False
    assert result["detail"] == "unsupported_ownership"
    result = asyncio.run(plugin.set_tdp_watts(20, "global", None, "42"))
    assert result["ok"] is True


def test_gpu_global_fields_are_read_only_and_do_not_change_effective_profile(Plugin):
    plugin = owned_plugin(Plugin)
    plugin._gpu_profiles.set_clock("global", True, 300, 700)
    plugin._gpu_profiles.set_clock("game", True, 500, 900, "42")
    state = asyncio.run(plugin.get_gpu_clock())
    assert state["global_manual"] is True
    assert (state["global_min"], state["global_max"]) == (300, 700)
    assert state["appid"] == "42"
    assert plugin._gpu_profiles.clock("42")["min"] == 500


@pytest.mark.parametrize("mode", ["auto", "manual"])
def test_steam_gpu_presentation_uses_live_mode_and_window_not_saved_game(Plugin, monkeypatch, mode):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._gpu_profiles.set_clock("global", True, 300, 700)
    plugin._gpu_profiles.set_clock("game", True, 400, 800, "42")
    plugin._gpu_profiles.set_follow_global("42", True)
    monkeypatch.setattr(plugin._gpu_clock, "capture_state", lambda: {"level": mode, "window": (500, 900)})
    before = copy.deepcopy(plugin._gpu_profiles._data)
    state = asyncio.run(plugin.get_gpu_clock())
    assert state["manual"] is (mode == "manual")
    assert state["display_source"] == "steam_live"
    assert state["steam_readback_available"] is True
    assert (state["min"], state["max"]) == (500, 900)
    assert (state["global_min"], state["global_max"]) == (300, 700)
    assert state["follows_global"] is False
    assert plugin._gpu_profiles._data == before


def test_steam_tdp_presentation_uses_live_ppt_even_when_saved_game_follows_global(Plugin, monkeypatch):
    from tdp.types import RailReading, TdpObservation

    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._tdp_profiles.set_pl1("global", 9)
    plugin._tdp_profiles.set_pl1("game", 7, "42")
    plugin._tdp_profiles.set_follow_global("42", True)
    plugin._tdp_backend.primary_rail = "pl2"
    observation = TdpObservation(True, {"steamdeck-hwmon": {
        "pl2": RailReading(12), "pl3": RailReading(15),
    }})
    before = copy.deepcopy(plugin._tdp_profiles._data)
    state = plugin._tdp_state(observation)
    assert state["watts"] == 12
    assert state["display_source"] == "steam_live"
    assert state["steam_readback_available"] is True
    assert state["levels"] == {"pl1": 12, "pl2": 12, "pl3": 15}
    assert state["global_watts"] == 9
    assert state["follows_global"] is False
    assert plugin._tdp_profiles._data == before


def test_unreadable_steam_state_preserves_types_and_labels_saved_values(Plugin, monkeypatch):
    from tdp.types import TdpObservation

    plugin = deck_owned_plugin(Plugin, monkeypatch)
    monkeypatch.setattr(plugin._gpu_clock, "capture_state", lambda: None)
    gpu = asyncio.run(plugin.get_gpu_clock())
    tdp = plugin._tdp_state(TdpObservation(False))
    assert type(gpu["manual"]) is bool
    assert type(tdp["watts"]) is int
    for state in (gpu, tdp):
        assert state["display_source"] == "saved"
        assert state["steam_readback_available"] is False


def test_capability_loss_keeps_steam_ownership_and_blocks_tdp_until_recovery(Plugin):
    plugin = owned_plugin(Plugin)
    before = plugin._game_power_owner_state()
    plugin._gpu_clock.supported = False
    degraded = plugin._game_power_owner_state()
    assert degraded["owner"] == "steam"
    assert degraded["write_allowed"] is False
    assert degraded["supported"] is False
    assert degraded["reason"] == "ownership_capability_lost"
    result = plugin._apply_tdp_targets({"pl1": 10, "pl2": 10, "pl3": 10}, True, False)
    assert result.ok is False
    assert plugin._tdp_backend.set_levels_calls == 0
    plugin._gpu_clock.supported = True
    assert plugin._game_power_owner_state() == before


def test_observations_continue_during_capability_loss_for_context_recovery(Plugin, monkeypatch):
    plugin = owned_plugin(Plugin)
    plugin._gpu_clock.supported = False
    monkeypatch.setattr(plugin, "_reapply_all", lambda **kw: None)
    asyncio.run(plugin.set_current_game("43", "Other game", "inactive"))
    assert plugin._power_ownership.state()["steam_profile"] == "inactive"
    assert plugin._game_power_write_allowed() is False
    plugin._gpu_clock.supported = True
    recovered = plugin._game_power_owner_state()
    assert recovered["context_appid"] == "43"
    assert recovered["owner"] == "pdc"
    assert recovered["write_allowed"] is True


def test_never_observed_unavailable_deck_keeps_legacy_permission(Plugin):
    plugin = Plugin()
    plugin._init()
    plugin._device = next(p for p in DEVICE_TABLE if p.key == "steam_deck_oled")
    plugin._gpu_clock.supported = False
    assert plugin._game_power_write_allowed() is True
    assert plugin._game_power_owner_state()["reason"] == "unsupported_ownership"


@pytest.mark.parametrize("failure", [None, "owner", "marker"])
def test_release_to_steam_finishes_gpu_ownership_without_hardware_write(Plugin, monkeypatch, failure):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._power_ownership.set_owner("42", "pdc", plugin._power_ownership.state()["revision"])
    plugin._settings["gpu_handoff_pending"] = True
    plugin._gpu_owned = True
    writes = []
    monkeypatch.setattr(plugin._gpu_clock, "set_auto", lambda: writes.append("auto") or True)
    save_settings = plugin._save
    if failure:
        def fail(*args, **kwargs):
            raise OSError("disk failure")
        monkeypatch.setattr(plugin._power_ownership if failure == "owner" else plugin,
                            "set_owner" if failure == "owner" else "_save", fail)
    result = asyncio.run(plugin.set_game_power_owner(
        "42", "steam", plugin._power_ownership.state()["revision"]
    ))
    assert result["ok"] is (failure is None)
    assert result["owner"] == ("pdc" if failure == "owner" else "steam")
    assert plugin._settings["gpu_handoff_pending"] is (failure is not None)
    assert plugin._gpu_owned is (failure is not None)
    if failure is None:
        assert plugin._release_gpu_clock_sync("unload") is True
        assert asyncio.run(plugin._release_gpu_clock("module-disabled")) is True
    if failure == "marker":
        monkeypatch.setattr(plugin, "_save", save_settings)
        retried = asyncio.run(plugin.set_game_power_owner(
            "42", "steam", plugin._power_ownership.state()["revision"]
        ))
        assert retried["ok"]
        assert not plugin._settings["gpu_handoff_pending"]
        assert not plugin._gpu_owned
        assert plugin._release_gpu_clock_sync("unload") is True
    assert writes == []


@pytest.mark.parametrize("auto", [False, True])
def test_global_gpu_edits_during_reset_do_not_persist(Plugin, monkeypatch, auto):
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._set_current_appid(None)
    plugin._power_ownership.observe(None, "inactive")
    plugin._gpu_profiles.set_clock("global", True, 300, 700)
    previous = copy.deepcopy(plugin._gpu_profiles._data)
    async def run():
        begun = await plugin.begin_game_power_reset(None, plugin._power_ownership.state()["revision"])
        assert begun["ok"]
        if auto:
            await plugin.set_gpu_clock_auto("global", None, None)
        else:
            await plugin.set_gpu_clock(600, 1000, "global", None, None)
        assert plugin._gpu_profiles._data == previous
        assert (await plugin.finish_game_power_reset(begun["token"], {}))["ok"]
    asyncio.run(run())


@pytest.mark.parametrize("saved_owner", ["steam", "pdc"])
@pytest.mark.parametrize("context", ["steam_game", "pdc_game", "global", "saved_game"])
def test_reload_waits_for_context_before_applying_global_power(Plugin, monkeypatch, saved_owner, context):
    from power_ownership import PowerOwnershipStore
    plugin = deck_owned_plugin(Plugin, monkeypatch)
    plugin._power_ownership.set_owner("42", saved_owner, plugin._power_ownership.state()["revision"])
    plugin._power_ownership = PowerOwnershipStore(plugin._power_ownership._path)
    plugin._current_appid = None
    writes = []
    monkeypatch.setattr(plugin._gpu_clock, "set", lambda lo, hi: writes.append((lo, hi)) or True)
    monkeypatch.setattr(plugin._gpu_clock, "get", lambda: (200, 1600))
    assert not plugin._game_power_write_allowed()
    plugin._run_gpu_clock({"mode": "manual", "min_mhz": 200, "max_mhz": 1600})
    plugin._tdp_guard_tick()
    assert writes == []
    assert plugin._tdp_backend.set_levels_calls == 0
    appid, observation = {
        "steam_game": ("43", "active"), "pdc_game": ("43", "inactive"),
        "global": (None, "inactive"), "saved_game": ("42", "active"),
    }[context]
    plugin._set_current_appid(appid)
    plugin._power_ownership.observe(appid, observation)
    allowed = context != "steam_game" and (context != "saved_game" or saved_owner == "pdc")
    assert plugin._game_power_write_allowed() is allowed
    plugin._run_gpu_clock({"mode": "manual", "min_mhz": 200, "max_mhz": 1600})
    assert writes == ([(200, 1600)] if allowed else [])


def test_saved_game_choices_do_not_gate_unsupported_platform(Plugin):
    from power_ownership import PowerOwnershipStore
    plugin = Plugin()
    plugin._init()
    plugin._power_ownership.set_context("42")
    plugin._power_ownership.set_owner("42", "steam", plugin._power_ownership.state()["revision"])
    plugin._power_ownership = PowerOwnershipStore(plugin._power_ownership._path)
    assert not plugin._game_power_ownership_supported()
    assert plugin._game_power_write_allowed()
