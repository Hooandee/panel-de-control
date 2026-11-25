import asyncio

from test_tdp_guard_rpc import plugin  # noqa: F401


def test_accessories_state_off_on_other_machines_without_serial_io(plugin, monkeypatch):  # noqa: F811
    from accessories.jsaux_pixel import detect
    monkeypatch.setattr(detect, "find_panel", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no io")))
    state = asyncio.run(plugin.get_accessories_state())
    assert state["supported"] is False
    assert state["present"] is False


def test_unknown_scene_is_an_error_not_a_write(plugin):  # noqa: F811
    result = asyncio.run(plugin.set_accessory_scene("nope", {}))
    assert result["ok"] is False


def test_session_start_time_is_stable_between_ticks(plugin):  # noqa: F811
    import time as _time
    plugin._current_appid = "1145360"
    plugin._current_appid_at = _time.monotonic() - 1800
    first = plugin._pixel_context()["game"]["started_at"]
    _time.sleep(0.01)
    assert plugin._pixel_context()["game"]["started_at"] == first
    assert isinstance(first, int)
    plugin._current_appid_at = _time.monotonic()
    assert plugin._pixel_context()["game"]["started_at"] - first >= 1799


def test_reports_keep_the_weather_city_out(plugin, monkeypatch):  # noqa: F811
    city = {"name": "Sevilla", "lat": 37.39, "lon": -5.98}

    async def state():
        return {"scene": "weather", "options": {"city": city, "theme": "aurora"}, "game_options": {}, "catalog": [1]}

    monkeypatch.setattr(plugin, "get_accessories_state", state)
    report = asyncio.run(plugin._accessories_report_state())
    assert report["options"] == {"city": True, "theme": "aurora"}
    assert "catalog" not in report
    assert "Sevilla" not in repr(report)
