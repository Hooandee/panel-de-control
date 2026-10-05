import asyncio
import sys

from kiosk.displays import Detection
from kiosk.rpc import public_rpc_methods
from test_tdp_guard_rpc import plugin  # noqa: F401


def _no_display(plugin):  # noqa: F811
    plugin._kiosk._detect = lambda: Detection(None, "no_mechanism")


def test_kiosk_setting_survives_a_restart(plugin):  # noqa: F811
    _no_display(plugin)
    state = asyncio.run(plugin.set_kiosk_enabled(True))
    assert state["enabled"] is True and state["supported"] is False
    main = sys.modules["main"]
    reloaded = main.Plugin()
    reloaded._init()
    assert reloaded._settings["kiosk_enabled"] is True
    assert reloaded._kiosk.enabled is True


def test_kiosk_state_is_reported_without_side_effects(plugin):  # noqa: F811
    _no_display(plugin)
    state = asyncio.run(plugin.get_kiosk_state())
    assert state == {
        "supported": False,
        "available": False,
        "reason": "no_mechanism",
        "enabled": False,
        "running": False,
        "mechanism": None,
        "last_error": None,
        "screen_off": False,
        "brightness": None,
    }


def test_support_log_records_the_kiosk_setting(plugin):  # noqa: F811
    _no_display(plugin)
    asyncio.run(plugin.set_kiosk_enabled(True))
    assert plugin._support_settings_state()["kiosk_enabled"] is True


def test_kiosk_rpcs_match_what_decky_exposes(plugin):  # noqa: F811
    methods = public_rpc_methods(plugin)
    assert {"get_kiosk_state", "set_kiosk_enabled", "get_tdp_state", "get_ui_prefs"} <= methods
    assert not any(name.startswith("_") for name in methods)


def test_kiosk_game_name_comes_from_the_steam_library(plugin, tmp_path, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(main.kiosk_steam_game, "game_name", lambda home, appid: "Stardew Valley" if appid == "413150" else None)
    assert asyncio.run(plugin.get_kiosk_game("413150")) == {"appid": "413150", "name": "Stardew Valley"}
    assert asyncio.run(plugin.get_kiosk_game("1")) == {"appid": "1", "name": None}


def test_steam_actions_report_failures_instead_of_raising(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(main.decky, "emit", None, raising=False)
    assert asyncio.run(plugin.kiosk_steam("brightness.get", [])) == {"ok": False, "error": "unsupported"}
    assert asyncio.run(plugin.kiosk_steam("rm -rf", [])) == {"ok": False, "error": "unknown_action"}


def test_kiosk_frame_rate_holds_the_readers_only_while_polled(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    events = []
    monkeypatch.setattr(plugin._gamescope_stats, "start", lambda: events.append("stats"))
    monkeypatch.setattr(plugin._gamescope_stats, "stop", lambda: events.append("stats-stop"))
    monkeypatch.setattr(plugin._gamescope_stats, "peek", lambda: {"fps": 120.0, "reason": "ok"})
    monkeypatch.setattr(plugin._gamescope_perf, "start", lambda: events.append("perf"))
    monkeypatch.setattr(plugin._gamescope_perf, "stop", lambda: events.append("perf-stop"))
    monkeypatch.setattr(plugin._gamescope_perf, "fps", lambda: 14.04)
    now = [1000.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: now[0])

    plugin._current_appid = None
    assert asyncio.run(plugin.get_kiosk_live()) == {"fps": 14.0, "reason": "ok", "playing_s": None, "appid": None}
    assert events == ["perf", "stats"]
    asyncio.run(plugin._sync_auto_stats_reader(False))
    assert events == ["perf", "stats", "perf"]
    now[0] += main._KIOSK_FPS_HOLD_S + 1
    asyncio.run(plugin._sync_auto_stats_reader(False))
    assert events == ["perf", "stats", "perf", "perf-stop", "stats-stop"]
    asyncio.run(plugin._sync_auto_stats_reader(False))
    assert events[-1] == "stats-stop"


def test_kiosk_session_names_the_game_without_starting_frame_readers(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    events = []
    monkeypatch.setattr(plugin._gamescope_stats, "start", lambda: events.append("stats"))
    monkeypatch.setattr(plugin._gamescope_perf, "start", lambda: events.append("perf"))
    now = [1000.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: now[0])
    plugin._current_appid = "894020"
    plugin._current_appid_at = 880.0
    assert asyncio.run(plugin.get_kiosk_session()) == {"playing_s": 120, "appid": "894020"}
    assert events == []
    assert not plugin._kiosk_wants_fps()


def test_kiosk_brightness_is_saved_only_when_the_panel_took_it(plugin, monkeypatch):  # noqa: F811
    async def took(value):
        return round(value, 3)

    async def refused(_value):
        return None

    monkeypatch.setattr(plugin._kiosk, "set_brightness", took)
    assert asyncio.run(plugin.set_kiosk_brightness(0.42)) == {"value": 0.42}
    assert plugin._settings["kiosk_brightness"] == 0.42
    monkeypatch.setattr(plugin._kiosk, "set_brightness", refused)
    assert asyncio.run(plugin.set_kiosk_brightness(0.9)) == {"value": None}
    assert plugin._settings["kiosk_brightness"] == 0.42


def test_kiosk_frame_rate_says_why_it_is_missing(plugin, monkeypatch):  # noqa: F811
    monkeypatch.setattr(plugin._gamescope_stats, "start", lambda: None)
    monkeypatch.setattr(plugin._gamescope_perf, "start", lambda: None)
    monkeypatch.setattr(plugin._gamescope_perf, "fps", lambda: None)
    monkeypatch.setattr(plugin._gamescope_stats, "peek", lambda: {"fps": None, "reason": "no_game_focus"})
    assert asyncio.run(plugin.get_kiosk_live())["reason"] == "no_game_focus"
    monkeypatch.setattr(plugin._gamescope_stats, "peek", lambda: {"fps": 120.0, "reason": "ok"})
    live = asyncio.run(plugin.get_kiosk_live())
    assert (live["fps"], live["reason"]) == (None, "fps_unavailable")


def test_focused_app_comes_from_gamescope_then_the_running_game(plugin, monkeypatch):  # noqa: F811
    monkeypatch.setattr(plugin._gamescope_stats, "focus", lambda: "812140")
    assert plugin._gamescope_focus_app() == 812140
    monkeypatch.setattr(plugin._gamescope_stats, "focus", lambda: "steam")
    plugin._current_appid = "413150"
    assert plugin._gamescope_focus_app() is None
    monkeypatch.setattr(plugin._gamescope_stats, "focus", lambda: None)
    assert plugin._gamescope_focus_app() == 413150
    plugin._current_appid = "ns:abc"
    assert plugin._gamescope_focus_app() is None


def test_kiosk_session_time_counts_from_when_the_game_appeared(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(plugin._gamescope_stats, "peek", lambda: {"fps": None, "reason": "no_game"})
    monkeypatch.setattr(plugin, "_apply_stats_reader", lambda: asyncio.sleep(0))
    now = [500.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: now[0])
    plugin._set_current_appid("1145360")
    now[0] += 4321.4
    assert asyncio.run(plugin.get_kiosk_live())["playing_s"] == 4321
    plugin._set_current_appid(None)
    assert asyncio.run(plugin.get_kiosk_live())["playing_s"] is None


def test_kiosk_stop_leaves_room_inside_deckys_unload_grace(plugin):  # noqa: F811
    main = sys.modules["main"]
    decky_sigkill_after_s = 5.0
    assert main._KIOSK_STOP_TIMEOUT_S <= decky_sigkill_after_s / 2


def test_kiosk_vitals_join_clocks_with_the_battery_reading(plugin, monkeypatch):  # noqa: F811
    main = sys.modules["main"]
    monkeypatch.setattr(main.kiosk_vitals, "read", lambda: {"cpu_mhz": 2093, "gpu_mhz": 220, "ram_used_gb": 5.4, "ram_total_gb": 11.2})
    monkeypatch.setattr(plugin._battery, "read", lambda: {"power_now_w": 8.7, "status": "Discharging"})
    monkeypatch.setattr(plugin._fan_reader, "fan_rpms", lambda: [3100, 0])
    monkeypatch.setattr(plugin._fan_reader, "driving_temps", lambda: (71.5, 64.0))
    assert asyncio.run(plugin.get_kiosk_vitals()) == {
        "cpu_mhz": 2093, "gpu_mhz": 220, "ram_used_gb": 5.4, "ram_total_gb": 11.2,
        "watts": 8.7, "charging": False, "fan_rpm": 3100, "celsius": 71.5,
    }


def test_frame_helper_runs_the_system_python_through_the_session(plugin, monkeypatch):  # noqa: F811
    from user_session import UserSession

    monkeypatch.setattr(plugin._kiosk, "session", lambda: None)
    assert plugin._native_frame_helper(["/fex/python3", "/plugin/gamescope_perf.py", "--child", "/"]) is None
    monkeypatch.setattr(plugin._kiosk, "session", lambda: UserSession(1000, "/run/user/1000", "armada"))
    command, env, _identity = plugin._native_frame_helper(["/fex/python3", "/plugin/gamescope_perf.py", "--child", "/"])
    assert command[1:] == ["--user", "--pipe", "--quiet", "--collect", "/usr/bin/python3", "/plugin/gamescope_perf.py", "--child", "/"]
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"


def test_reports_carry_the_bottom_screen_state(plugin):  # noqa: F811
    state = plugin._kiosk_report_state()
    assert {"enabled", "running", "reason", "screen_off", "brightness", "rpc_calls"} <= set(state)


def test_stock_distro_hostnames_are_not_scrubbed_from_reports(plugin, monkeypatch):  # noqa: F811
    import socket

    plugin._os_id = "armada"
    monkeypatch.setattr(socket, "gethostname", lambda: "armada")
    assert plugin._redact_ids()[1] is None
    monkeypatch.setattr(socket, "gethostname", lambda: "steamdeck")
    assert plugin._redact_ids()[1] is None
    monkeypatch.setattr(socket, "gethostname", lambda: "juans-thor")
    assert plugin._redact_ids()[1] == "juans-thor"


def test_bridge_replies_stay_out_of_the_journal(plugin):  # noqa: F811
    main = sys.modules["main"]
    assert not hasattr(main.Plugin.kiosk_steam_result, "__wrapped__")
    assert hasattr(main.Plugin.kiosk_steam, "__wrapped__")
