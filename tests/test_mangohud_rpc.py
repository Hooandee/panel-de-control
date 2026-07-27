"""RPC-level tests for the HUD (MangoHud overlay) tab."""
import asyncio
import concurrent.futures
import importlib
import os
import sys
import types


def _make_plugin(tmp_path, monkeypatch):
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
    config_file=None,
    running=True,
):
    """Point detection at a tmp presets.conf and control `supported`."""
    monkeypatch.setattr(
        main.mangohud_detect, "detect",
        lambda **_kwargs: {"running": running, "supported": supported,
                 "presetsPath": presets_path, "configFile": config_file},
    )


def _items(*ids):
    return [{"kind": "metric", "id": i} for i in ids]


def test_get_hud_state_shape(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, str(tmp_path / "presets.conf"))
    st = asyncio.run(p.get_hud_state())
    assert st["supported"] is True
    assert st["model"]["enabled"] is False
    assert "fps" in st["catalog"]
    assert "balanced" in st["presets"]
    assert st["capability"] == "ready"
    assert st["applyStatus"] == "disabled"
    assert st["values"] == {}


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


def test_running_without_preset_support_is_explicitly_unavailable(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False, running=True)

    st = asyncio.run(p.set_hud_enabled(True))

    assert st["capability"] == "unsupported"
    assert st["applyStatus"] == "unavailable"
    assert not os.path.exists(presets)


def test_set_config_persists_but_does_not_write_while_disabled(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
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
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: calls.append(True) or True, raising=False)

    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert calls == [True]


def test_successful_write_and_reload_reports_applied(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: True, raising=False)

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "applied"


def test_failed_reload_reports_pending_not_success(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: False, raising=False)

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "pending"


def test_failed_write_readback_reports_failure(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(main, "apply_hud", lambda *a, **k: None, raising=False)

    st = asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))

    assert st["applyStatus"] == "failed"


def test_failed_clear_reports_failure(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: True, raising=False)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    monkeypatch.setattr(main, "clear_presets", lambda _path: False, raising=False)

    st = asyncio.run(p.set_hud_enabled(False))

    assert st["applyStatus"] == "failed"


def test_disabling_hud_requests_mangoapp_reload(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    calls = []
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: calls.append(True) or True, raising=False)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    calls.clear()

    asyncio.run(p.set_hud_enabled(False))

    assert calls == [True]


def test_unsupported_overlay_never_writes(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets, supported=False)
    st = asyncio.run(p.set_hud_enabled(True))
    assert st["supported"] is False
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
    _fake_overlay(main, monkeypatch, presets, config_file=live)
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
    _fake_overlay(main, monkeypatch, presets, config_file=live)
    asyncio.run(p.set_hud_config({"items": _items("fps"), "enabled": True}))
    asyncio.run(p.set_hud_enabled(False))
    assert open(live).read() == steam_config  # Steam's file untouched throughout
    assert not os.path.exists(presets)


def test_pdc_metric_bakes_value_into_presets_no_state_file(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    asyncio.run(p.set_hud_config({"items": _items("fps", "pdc_tdp"), "enabled": True}))
    # The row is a single baked custom_text=<label> <value> line — no exec, no state file.
    setpoint = asyncio.run(p.get_power_draw())["setpoint"]
    conf = open(presets).read()
    assert f"custom_text=TDP {setpoint}W" in conf
    assert "exec=" not in conf
    assert not os.path.exists(str(tmp_path / "pdc_tdp.txt"))


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
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: calls.append(True) or True, raising=False)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    calls.clear()

    p._settings["eco_enabled"] = True
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

    monkeypatch.setattr(main, "reload_mangoapp", reload, raising=False)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))

    asyncio.run(p._refresh_pdc_metrics())

    assert calls == [True, True]


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


def test_pdc_refresh_uses_serial_apply_executor(tmp_path, monkeypatch):
    presets = str(tmp_path / "presets.conf")
    main, p = _make_plugin(tmp_path, monkeypatch)
    _fake_overlay(main, monkeypatch, presets)
    monkeypatch.setattr(main, "reload_mangoapp", lambda *_args: True, raising=False)
    asyncio.run(p.set_hud_config({"items": _items("pdc_eco"), "enabled": True}))
    executor = _RecordingExecutor()
    p._apply_executor = executor
    p._settings["eco_enabled"] = True

    asyncio.run(p._refresh_pdc_metrics())

    assert executor.count == 1


def test_zero_fan_rpm_is_a_real_reading(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._pdc_active_ids = ["pdc_fan_rpm"]
    monkeypatch.setattr(p, "_read_fans", lambda: {"fans": [{"rpm": 0}]})

    assert p._pdc_values() == {"pdc_fan_rpm": "0"}


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


def test_hud_refresh_failure_does_not_skip_the_rest_of_auto_tick(tmp_path, monkeypatch):
    main, p = _make_plugin(tmp_path, monkeypatch)
    p._init()
    p._current_appid = None
    sleeps = 0
    resets = []

    async def sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    async def fail_refresh():
        raise OSError("presets unavailable")

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(p, "_refresh_pdc_metrics", fail_refresh)
    monkeypatch.setattr(p, "_reset_auto_windows", lambda: resets.append(True))

    asyncio.run(p._auto_loop())

    assert resets == [True]
