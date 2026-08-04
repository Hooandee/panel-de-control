"""RPC-level tests for the HUD (MangoHud overlay) tab."""
import asyncio
import concurrent.futures
import importlib
import os
import sys
import threading
import types

import pytest

from mangohud.observations import TimedValue


def _make_plugin(tmp_path, monkeypatch):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.DECKY_USER_HOME = str(tmp_path)
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = True
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=20)

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
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": False)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": False, raising=False)
    return main, main.Plugin()


def _fake_overlay(
    main,
    monkeypatch,
    presets_path,
    supported=True,
    running=True,
):
    """Point detection at a tmp presets.conf and control `supported`."""
    sessions = (
        (
            main.mangohud_detect.HudSession(
                pid=4242,
                starttime=9001,
                uid=os.getuid(),
                cwd=str(os.path.dirname(presets_path)),
                presets_path=presets_path,
                presets_supported=supported,
            ),
        )
        if running
        else ()
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "detect_sessions",
        lambda **_kwargs: sessions,
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "session_alive",
        lambda _session, **_kwargs: True,
    )

    _set_reload(main, monkeypatch, lambda: True)


def _set_reload(main, monkeypatch, request):
    def reload_snapshot(snapshot, **_kwargs):
        identities = tuple((session.pid, session.starttime) for session in snapshot)
        requested = identities if request() else ()
        pending = () if requested else identities
        return types.SimpleNamespace(requested=requested, pending=pending)

    monkeypatch.setattr(main, "reload_sessions", reload_snapshot, raising=False)


def _items(*ids):
    return [{"kind": "metric", "id": i} for i in ids]


def test_get_hud_state_shape(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, str(tmp_path / "presets.conf"))
    st = asyncio.run(p.get_hud_state())
    assert st["model"]["enabled"] is False
    assert st["capability"] == "ready"
    assert st["applyStatus"] == "disabled"
    assert st["values"] == {}


def test_hud_detection_fails_closed_when_user_ownership_is_unknown(
    tmp_path,
    monkeypatch,
):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._hud_owner = None
    monkeypatch.setattr(
        main.mangohud_detect,
        "detect_sessions",
        lambda **_kwargs: pytest.fail("must not scan sessions without a trusted uid"),
    )

    state = asyncio.run(p.get_hud_state())

    assert state["capability"] == "inactive"


def test_same_game_name_hydration_only_refreshes_hud(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._current_appid = "42"
    p._current_game_name = "42"
    reapplies = []
    refreshes = []
    monkeypatch.setattr(p, "_reapply_all", lambda: reapplies.append(True))

    async def refresh():
        refreshes.append(True)

    async def state():
        return {"ok": True}

    monkeypatch.setattr(p, "_refresh_pdc_metrics", refresh)
    monkeypatch.setattr(p, "get_tdp_state", state)

    result = asyncio.run(p.set_current_game("42", "Hydrated name"))

    assert result == {"ok": True}
    assert p._current_game_name == "Hydrated name"
    assert refreshes == [True]
    assert reapplies == []


def test_offline_hud_stays_editable_and_pending_without_writing(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False, running=False)

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["capability"] == "inactive"
    assert st["applyStatus"] == "pending"
    assert st["model"]["enabled"] is True
    assert not os.path.exists(presets)


def test_pending_hud_recovers_when_a_supported_session_appears(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False, running=False)
    state = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert state["applyStatus"] == "pending"

    _fake_overlay(main, monkeypatch, presets)
    state = asyncio.run(p.get_hud_state())

    assert state["applyStatus"] == "reload_requested"
    assert os.path.exists(presets)


def test_unavailable_hud_recovers_when_preset_support_appears(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False, running=True)
    state = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert state["applyStatus"] == "unavailable"

    _fake_overlay(main, monkeypatch, presets)
    state = asyncio.run(p.get_hud_state())

    assert state["applyStatus"] == "reload_requested"
    assert os.path.exists(presets)


def test_ambiguous_hud_recovers_when_sessions_converge_on_one_path(
    tmp_path,
    monkeypatch,
):
    main, p = _make_plugin(tmp_path, monkeypatch)
    first = str(tmp_path / "first" / "presets.conf")
    second = str(tmp_path / "second" / "presets.conf")
    sessions = (
        main.mangohud_detect.HudSession(
            20, 9001, os.getuid(), str(tmp_path), first, True
        ),
        main.mangohud_detect.HudSession(
            21, 9002, os.getuid(), str(tmp_path), second, True
        ),
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "detect_sessions",
        lambda **_kwargs: sessions,
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "session_alive",
        lambda _session, **_kwargs: True,
    )
    state = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert state["applyStatus"] == "ambiguous"

    _fake_overlay(main, monkeypatch, first)
    state = asyncio.run(p.get_hud_state())

    assert state["applyStatus"] == "reload_requested"
    assert os.path.exists(first)


def test_offline_disable_clears_the_remembered_custom_path(tmp_path, monkeypatch):
    custom = str(tmp_path / "custom" / "presets.conf")
    default = str(tmp_path / "default" / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, custom)

    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert os.path.exists(custom)
    assert p._settings["hud_managed_path"] == custom

    _fake_overlay(main, monkeypatch, default, supported=False, running=False)
    st = asyncio.run(p.set_hud_enabled(False))

    assert st["applyStatus"] == "disabled"
    assert not os.path.exists(custom)
    assert not os.path.exists(f"{custom}.pdc-managed")
    assert p._settings["hud_managed_path"] is None


def test_supported_path_change_restores_the_previous_managed_file(tmp_path, monkeypatch):
    previous = str(tmp_path / "previous" / "presets.conf")
    current = str(tmp_path / "current" / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, previous)

    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert os.path.exists(previous)

    _fake_overlay(main, monkeypatch, current)
    st = asyncio.run(p.reload_hud())

    assert st["applyStatus"] == "reload_requested"
    assert not os.path.exists(previous)
    assert not os.path.exists(f"{previous}.pdc-managed")
    assert os.path.exists(current)
    assert p._settings["hud_managed_path"] == current


def test_running_without_preset_support_is_explicitly_unavailable(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False, running=True)

    st = asyncio.run(p.set_hud_enabled(True))

    assert st["capability"] == "unsupported"
    assert st["applyStatus"] == "unavailable"
    assert not os.path.exists(presets)


def test_distinct_live_presets_paths_are_ambiguous_and_never_written(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    first = str(tmp_path / "first" / "presets.conf")
    second = str(tmp_path / "second" / "presets.conf")
    sessions = (
        main.mangohud_detect.HudSession(
            20, 9001, os.getuid(), str(tmp_path), first, True
        ),
        main.mangohud_detect.HudSession(
            21, 9002, os.getuid(), str(tmp_path), second, True
        ),
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "detect_sessions",
        lambda **_kwargs: sessions,
    )

    state = asyncio.run(
        p.set_hud_config({"items": _items("fps"), "enabled": True})
    )

    assert state["applyStatus"] == "ambiguous"
    assert not os.path.exists(first)
    assert not os.path.exists(second)


def test_set_config_persists_but_does_not_write_while_disabled(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    _fake_overlay(main, monkeypatch, presets)
    st = asyncio.run(p.set_hud_config({"items": _items("fps", "gpu"), "enabled": False}))
    assert st["model"]["items"] == _items("fps", "gpu")
    assert not os.path.exists(presets)  # disabled → stock, nothing hijacked


def test_enabling_writes_presets_conf_and_disabling_clears_it(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps", "gpu"), "enabled": False}))
    asyncio.run(p.set_hud_enabled(True))
    text = open(presets).read()
    assert "[preset 2]" in text and "gpu_stats" in text
    asyncio.run(p.set_hud_enabled(False))
    assert not os.path.exists(presets)  # handed back to stock


def test_writing_enabled_hud_requests_mangoapp_reload(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    calls = []
    _set_reload(main, monkeypatch, lambda: calls.append(True) or True)

    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert calls == [True]


def test_successful_write_and_reload_reports_requested_not_applied(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(
        main,
        "reload_sessions",
        lambda sessions: types.SimpleNamespace(
            requested=tuple((session.pid, session.starttime) for session in sessions),
            pending=(),
        ),
    )

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "reload_requested"


def test_set_config_scans_mangoapp_once(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    scans = []

    def detect_sessions(**_kwargs):
        scans.append(True)
        return (
            main.mangohud_detect.HudSession(
                4242, 9001, os.getuid(), str(tmp_path), presets, True
            ),
        )

    monkeypatch.setattr(main.mangohud_detect, "detect_sessions", detect_sessions)
    monkeypatch.setattr(
        main.mangohud_detect,
        "session_alive",
        lambda _session, **_kwargs: True,
    )
    monkeypatch.setattr(
        main,
        "reload_sessions",
        lambda sessions: types.SimpleNamespace(
            requested=tuple((session.pid, session.starttime) for session in sessions),
            pending=(),
        ),
    )

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "reload_requested"
    assert scans == [True]


def test_session_replaced_after_detection_prevents_write(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(
        main.mangohud_detect,
        "session_alive",
        lambda _session, **_kwargs: False,
    )

    state = asyncio.run(
        p.set_hud_config({"items": _items("fps"), "enabled": True})
    )

    assert state["applyStatus"] == "pending"
    assert not os.path.exists(presets)


def test_failed_reload_keeps_exact_file_readback_as_written(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    _set_reload(main, monkeypatch, lambda: False)

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "written"


def test_rejected_write_readback_reports_failure(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(
        main,
        "apply_hud",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("readback mismatch")),
        raising=False,
    )

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "failed"


def test_failed_clear_reports_failure(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    monkeypatch.setattr(
        main,
        "clear_presets",
        lambda _path, **_kwargs: False,
        raising=False,
    )

    st = asyncio.run(p.set_hud_enabled(False))

    assert st["applyStatus"] == "failed"


def test_external_edit_becomes_an_explicit_conflict_without_data_loss(
    tmp_path,
    monkeypatch,
):
    presets = str(tmp_path / "presets.conf")
    external = "fps\n"
    edited = "fps\ngpu_stats\n"
    os.makedirs(os.path.dirname(presets), exist_ok=True)
    with open(presets, "w") as handle:
        handle.write(external)
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    initial = asyncio.run(
        p.set_hud_config({"items": _items("fps"), "enabled": True})
    )
    assert initial["applyStatus"] == "conflict"
    asyncio.run(p.resolve_hud_conflict("use_pdc"))
    with open(presets, "w") as handle:
        handle.write(edited)

    state = asyncio.run(p.reload_hud())

    assert state["applyStatus"] == "conflict"
    assert state["conflict"]["path"] == "presets.conf"
    assert state["conflict"]["expectedHash"]
    assert state["conflict"]["actualHash"]
    assert open(presets).read() == edited
    assert open(f"{presets}.pdc-backup").read() == external


@pytest.mark.parametrize("action", ("keep_external", "use_pdc"))
def test_conflict_resolution_is_explicit_and_preserves_the_latest_external_edit(
    tmp_path,
    monkeypatch,
    action,
):
    presets = str(tmp_path / "presets.conf")
    original = "fps\n"
    edited = "fps\ngpu_stats\n"
    os.makedirs(os.path.dirname(presets), exist_ok=True)
    with open(presets, "w") as handle:
        handle.write(original)
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    with open(presets, "w") as handle:
        handle.write(edited)
    assert asyncio.run(p.reload_hud())["applyStatus"] == "conflict"

    state = asyncio.run(p.resolve_hud_conflict(action))

    assert state["conflict"] is None
    if action == "keep_external":
        assert state["model"]["enabled"] is False
        assert state["applyStatus"] == "disabled"
        assert open(presets).read() == edited
        assert not os.path.exists(f"{presets}.pdc-managed")
        assert not os.path.exists(f"{presets}.pdc-backup")
    else:
        assert state["model"]["enabled"] is True
        assert state["applyStatus"] == "reload_requested"
        assert open(presets).read() != edited
        assert open(f"{presets}.pdc-backup").read() == edited


def test_disabling_hud_requests_mangoapp_reload(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    calls = []
    _set_reload(main, monkeypatch, lambda: calls.append(True) or True)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    calls.clear()

    asyncio.run(p.set_hud_enabled(False))

    assert calls == [True]


def test_unsupported_overlay_never_writes(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False)
    st = asyncio.run(p.set_hud_enabled(True))
    assert st["capability"] == "unsupported"
    assert not os.path.exists(presets)


def test_reset_restores_default_model(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("time"), "enabled": True}))
    st = asyncio.run(p.reset_hud())
    assert st["model"]["items"] == main.mangohud_config.DEFAULT_MODEL["items"]


def test_enabling_writes_presets_and_never_touches_steam_live_config(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    live = str(tmp_path / "mangohud.config")
    steam_config = "control=mangohud\nmangoapp_steam\npreset=2\n"
    with open(live, "w") as handle:
        handle.write(steam_config)
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps", "gpu"), "enabled": True}))
    # SAFE MODE: our config only ever goes to presets.conf; Steam's live file is never
    # touched (writing it destabilises the overlay/slider).
    assert "gpu_stats=1" in open(presets).read()
    assert open(live).read() == steam_config


def test_disabling_never_touches_steam_live_config(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    live = str(tmp_path / "mangohud.config")
    steam_config = "control=mangohud\npreset=2\n"
    with open(live, "w") as handle:
        handle.write(steam_config)
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    asyncio.run(p.set_hud_enabled(False))
    assert open(live).read() == steam_config  # Steam's file untouched throughout
    assert not os.path.exists(presets)


def test_pdc_metric_bakes_applied_readback_not_profile_target(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    target = p._effective_levels(p._current_appid)[0]["pl1"]
    assert target != 11
    monkeypatch.setattr(p._tdp_backend, "read_applied", lambda: 11)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps", "pdc_tdp"), "enabled": True}))
    # The row is a single baked custom_text=<label> <value> line — no exec, no state file.
    conf = open(presets).read()
    assert "custom_text=TDP 11W" in conf
    assert f"custom_text=TDP {target}W" not in conf
    assert "exec=" not in conf
    assert not os.path.exists(str(tmp_path / "pdc_tdp.txt"))


def test_persisted_hud_locale_controls_dynamic_in_game_text(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)

    asyncio.run(p.set_hud_config({
        "locale": "en",
        "items": _items("pdc_eco"),
        "enabled": True,
    }))

    assert "custom_text=Download Inactive" in open(presets).read()


def test_changed_applied_tdp_refreshes_hud_without_profile_change(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    applied = {"watts": 11}
    monkeypatch.setattr(p._tdp_backend, "read_applied", lambda: applied["watts"])
    _fake_overlay(main, monkeypatch, presets)
    reloads = []
    _set_reload(main, monkeypatch, lambda: reloads.append(True) or True)

    asyncio.run(p.set_hud_config({"items": _items("pdc_tdp"), "enabled": True}))
    reloads.clear()
    applied["watts"] = 13
    p._hud_last_publish_at = 0.0
    monkeypatch.setattr(main, "_monotonic", lambda: 2.0)

    asyncio.run(p._refresh_pdc_metrics())

    assert "custom_text=TDP 13W" in open(presets).read()
    assert reloads == [True]


def test_tdp_without_readback_does_not_masquerade_as_profile_target(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    monkeypatch.setattr(p._tdp_backend, "read_applied", lambda: None)
    p._pdc_active_ids = ["pdc_tdp"]

    assert p._pdc_values() == {"pdc_tdp": "-"}


def test_pdc_tdp_uses_the_backends_primary_rail(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._tdp_backend.primary_rail = "pl2"
    observation = main.TdpObservation(
        readable=True,
        surfaces={
            p._tdp_backend.name: {
                "pl1": main.RailReading(10),
                "pl2": main.RailReading(17),
            },
        },
    )

    snapshot = p._pdc_snapshot(
        ["pdc_tdp"],
        {"tdp": main.TimedValue(observation, main._monotonic(), True)},
    )

    assert snapshot["applied"] == 17


def test_blocking_tdp_backend_reuses_reconciler_observation(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._tdp_backend.blocking = True
    p._tdp_observation = main.TdpObservation(
        readable=True,
        surfaces={p._tdp_backend.name: {"pl1": main.RailReading(9)}},
    )
    p._tdp_observation_at = main._monotonic()
    reads = []
    monkeypatch.setattr(
        p._tdp_backend,
        "read_applied",
        lambda: reads.append(True) or 12,
    )
    p._pdc_active_ids = ["pdc_tdp"]

    assert p._pdc_values() == {"pdc_tdp": "9W"}
    assert reads == []


def test_blocking_tdp_backend_does_not_refresh_stale_cached_observation(
    tmp_path,
    monkeypatch,
):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._tdp_backend.blocking = True
    p._tdp_observation = main.TdpObservation(
        readable=True,
        surfaces={p._tdp_backend.name: {"pl1": main.RailReading(9)}},
    )
    p._tdp_observation_at = 10.0
    p._pdc_active_ids = ["pdc_tdp"]
    monkeypatch.setattr(main, "_monotonic", lambda: 20.0)

    assert p._pdc_values() == {"pdc_tdp": "-"}


def test_pdc_custom_label_baked_with_value(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({
        "items": [{"kind": "metric", "id": "pdc_eco", "label": "Bateria"}],
        "enabled": True,
    }))
    assert "custom_text=Bateria Inactivo" in open(presets).read()


def test_pdc_metric_gone_from_presets_when_dropped(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    assert "pdc_eco" not in open(presets).read()  # no directive; but the label is baked
    assert "custom_text=Descarga Inactivo" in open(presets).read()
    # Drop the pdc metric → its baked row is gone from presets.conf.
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert "Descarga" not in open(presets).read()


def test_changed_pdc_value_reloads_running_mangoapp(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    calls = []
    _set_reload(main, monkeypatch, lambda: calls.append(True) or True)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    calls.clear()

    p._settings["eco_enabled"] = True
    p._hud_last_publish_at = 0.0
    monkeypatch.setattr(main, "_monotonic", lambda: 2.0)
    asyncio.run(p._refresh_pdc_metrics())

    assert "custom_text=Descarga Activo" in open(presets).read()
    assert calls == [True]


def test_failed_pdc_reload_is_retried_on_next_tick(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    results = iter((False, True))
    calls = []

    def reload(*_args):
        calls.append(True)
        return next(results)

    _set_reload(main, monkeypatch, reload)
    clock = {"now": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: clock["now"], raising=False)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))

    clock["now"] = 101.1
    asyncio.run(p._refresh_pdc_metrics())

    assert calls == [True, True]


def test_reload_retries_stop_after_the_bounded_attempt_budget(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    calls = []
    _set_reload(main, monkeypatch, lambda: calls.append(True) or False)
    clock = {"now": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: clock["now"], raising=False)

    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    for now in (101.1, 103.2, 107.3, 120.0):
        clock["now"] = now
        p._retry_pending_hud_reload()

    assert len(calls) == main._HUD_RELOAD_MAX_ATTEMPTS
    assert p._hud_reload_pending == ()


def test_partial_reload_retries_only_the_pending_session(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    first = main.mangohud_detect.HudSession(
        20, 9001, os.getuid(), str(tmp_path), presets, True
    )
    second = main.mangohud_detect.HudSession(
        21, 9002, os.getuid(), str(tmp_path), presets, True
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "detect_sessions",
        lambda **_kwargs: (first, second),
    )
    monkeypatch.setattr(
        main.mangohud_detect,
        "session_alive",
        lambda _session, **_kwargs: True,
    )
    calls = []

    def reload_sessions(sessions):
        calls.append(tuple(sessions))
        if len(calls) == 1:
            return types.SimpleNamespace(
                requested=((first.pid, first.starttime),),
                pending=((second.pid, second.starttime),),
            )
        return types.SimpleNamespace(
            requested=((second.pid, second.starttime),),
            pending=(),
        )

    monkeypatch.setattr(main, "reload_sessions", reload_sessions)
    clock = {"now": 100.0}
    monkeypatch.setattr(main, "_monotonic", lambda: clock["now"], raising=False)

    state = asyncio.run(
        p.set_hud_config({"items": _items("pdc_eco"), "enabled": True})
    )
    assert state["applyStatus"] == "written"

    clock["now"] = 101.1
    asyncio.run(p._refresh_pdc_metrics())

    assert calls == [(first, second), (second,)]
    assert p._hud_apply_status == "reload_requested"


def test_pdc_refresh_write_failure_reports_failed_and_stays_retryable(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    written = dict(p._pdc_written)
    p._settings["eco_enabled"] = True
    p._hud_last_publish_at = 0.0
    monkeypatch.setattr(main, "_monotonic", lambda: 2.0)

    def fail_write(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(main, "apply_hud", fail_write, raising=False)

    with pytest.raises(OSError, match="disk unavailable"):
        asyncio.run(p._refresh_pdc_metrics())

    assert p._hud_apply_status == "failed"
    assert p._pdc_written == written


class _RecordingExecutor(concurrent.futures.Executor):
    def __init__(self):
        self.count = 0

    def submit(self, fn, *args, **kwargs):
        self.count += 1
        future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future


def test_inactive_pdc_refresh_skips_executor(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    executor = _RecordingExecutor()
    p._apply_executor = executor
    p._pdc_active_ids = []
    p._pdc_presets_path = None

    asyncio.run(p._refresh_pdc_metrics())

    assert executor.count == 0


def test_pdc_refresh_does_not_use_the_shared_apply_executor(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    executor = _RecordingExecutor()
    p._apply_executor = executor
    p._settings["eco_enabled"] = True

    asyncio.run(p._refresh_pdc_metrics())

    assert executor.count == 0


def test_pdc_refresh_applies_multiple_changed_values_once(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({
        "items": _items("pdc_eco", "pdc_profile"),
        "enabled": True,
    }))

    apply_calls = []
    reload_calls = []
    original_apply_hud = main.apply_hud

    def apply_once(*args, **kwargs):
        apply_calls.append(True)
        return original_apply_hud(*args, **kwargs)

    monkeypatch.setattr(main, "apply_hud", apply_once, raising=False)
    _set_reload(main, monkeypatch, lambda: reload_calls.append(True) or True)
    p._settings["eco_enabled"] = True
    p._current_appid = "42"
    p._current_game_name = "Game"
    p._hud_last_publish_at = 0.0
    monkeypatch.setattr(main, "_monotonic", lambda: 2.0)

    asyncio.run(p._refresh_pdc_metrics())

    assert apply_calls == [True]
    assert reload_calls == [True]


def test_zero_fan_rpm_is_a_real_reading(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._pdc_active_ids = ["pdc_fan_rpm"]
    monkeypatch.setattr(p, "_read_fans", lambda: {"fans": [{"rpm": 0}]})

    assert p._pdc_values() == {"pdc_fan_rpm": "0"}


def test_empty_preread_battery_result_is_not_read_twice(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._pdc_active_ids = ["pdc_bat_health"]
    reads = []
    monkeypatch.setattr(
        p._battery,
        "read",
        lambda: reads.append(True) or {"health_percent": 99},
    )

    assert p._pdc_values({"battery": {}}) == {"pdc_bat_health": "-"}
    assert reads == []


def test_stale_or_unconfirmed_power_observation_renders_dash(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._pdc_active_ids = ["pdc_power"]
    monkeypatch.setattr(main, "_monotonic", lambda: 13.1)

    assert p._pdc_values({
        "power": TimedValue({"watts": 15}, 10.0, True),
    }) == {"pdc_power": "-"}
    assert p._pdc_values({
        "power": TimedValue({"watts": 15}, 13.0, False),
    }) == {"pdc_power": "-"}


def test_dynamic_hud_publication_is_bounded_to_one_per_second(
    tmp_path,
    monkeypatch,
):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    _fake_overlay(main, monkeypatch, presets)
    clock = {"now": 0.0}
    watts = {"value": 10.0}
    monkeypatch.setattr(main, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        p._power_reader,
        "read",
        lambda: {"watts": watts["value"], "gpu_busy": 99},
    )
    asyncio.run(p.set_hud_config({"items": _items("pdc_power"), "enabled": True}))
    publications = []

    def publish(model, path, values, **_kwargs):
        publications.append((clock["now"], dict(values)))
        return main.mangohud_config.build_presets_conf(model, values)

    monkeypatch.setattr(main, "apply_hud", publish)
    for sample in range(1, 3601):
        clock["now"] = sample / 10
        watts["value"] = 10 + sample / 100
        p._refresh_pdc_metrics_sync()

    assert len(publications) <= 360

    publications.clear()
    p._pdc_written = {"pdc_power": "15W"}
    for sample in range(1, 31):
        clock["now"] = 400 + sample / 10
        watts["value"] = 15.1 if sample % 2 else 15.4
        p._refresh_pdc_metrics_sync()

    assert publications == []


def test_unavailable_tdp_and_fan_capabilities_render_dashes(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._tdp_backend.supported = False
    p._fan_ctrl.supported = False
    p._pdc_active_ids = ["pdc_tdp", "pdc_auto_tdp", "pdc_fan", "pdc_eco"]

    assert p._pdc_values() == {
        "pdc_tdp": "-",
        "pdc_auto_tdp": "-",
        "pdc_fan": "-",
        "pdc_eco": "-",
    }


def test_auto_tick_offers_hud_refresh_without_awaiting_it(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._current_appid = None
    sleeps = 0
    resets = []
    offers = []

    async def sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    async def fail_if_awaited():
        raise AssertionError("auto loop awaited the HUD worker")

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(p, "_refresh_pdc_metrics", fail_if_awaited)
    monkeypatch.setattr(p, "_offer_pdc_refresh", lambda: offers.append(True), raising=False)
    monkeypatch.setattr(p, "_reset_auto_windows", lambda: resets.append(True))

    asyncio.run(p._auto_loop())

    assert offers == [True]
    assert resets == [True]


def test_offered_refresh_records_worker_failure(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._pdc_active_ids = ["pdc_power"]
    p._pdc_presets_path = str(tmp_path / "presets.conf")
    monkeypatch.setattr(
        p,
        "_refresh_pdc_metrics_sync",
        lambda: (_ for _ in ()).throw(OSError("presets unavailable")),
    )

    p._offer_pdc_refresh()
    p._hud_coordinator.call(p._hud_generation, lambda: None).result(timeout=1)

    assert p._pdc_refresh_failed is True
    p._hud_generation += 1
    p._hud_coordinator.close(p._hud_generation, lambda: None)


def test_prepare_shutdown_invalidates_hud_ingress_synchronously(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    generation = p._hud_generation

    p._prepare_shutdown()

    assert p._hud_shutdown is True
    assert p._hud_generation == generation + 1


def test_hud_save_entering_after_shutdown_never_reaches_store(tmp_path, monkeypatch):
    _main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    saves = []
    monkeypatch.setattr(p._hud, "save", lambda model: saves.append(model) or model)
    p._prepare_shutdown()

    with pytest.raises(RuntimeError, match="plugin_shutting_down"):
        asyncio.run(
            p.set_hud_config({"items": _items("fps"), "enabled": True})
        )

    assert saves == []


@pytest.mark.parametrize("method", ("_unload", "_uninstall"))
def test_shutdown_restores_managed_hud_for_unload_and_uninstall(
    tmp_path,
    monkeypatch,
    method,
):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    assert os.path.exists(presets)
    monkeypatch.setattr(p, "_perform_shutdown_handoff", lambda *_args: None)
    monkeypatch.setattr(p, "_drain_offloaded_sync", lambda *_args: True)
    monkeypatch.setattr(p, "_shutdown_apply_executor", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main.fan_expose, "remove_conf", lambda: None)

    asyncio.run(getattr(p, method)())

    assert not os.path.exists(presets)
    assert not os.path.exists(f"{presets}.pdc-managed")


def test_refresh_queued_before_shutdown_cannot_rewrite_after_restore(
    tmp_path,
    monkeypatch,
):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    p._hud_coordinator.call(
        p._hud_generation,
        lambda: (started.set(), release.wait(timeout=2)),
    )
    assert started.wait(timeout=1)
    queued = p._hud_coordinator.submit_latest(
        p._hud_generation,
        p._apply_hud,
    )
    closer = threading.Thread(target=lambda: (p._prepare_shutdown(), closed.set()))
    closer.start()
    assert not closed.wait(timeout=0.05)

    release.set()
    closer.join(timeout=1)

    assert queued.cancelled()
    assert closed.is_set()
    assert not os.path.exists(presets)
    assert not os.path.exists(f"{presets}.pdc-managed")
