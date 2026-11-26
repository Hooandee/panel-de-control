import asyncio

from test_tdp_guard_rpc import plugin  # noqa: F401


def test_other_machines_never_touch_the_serial_port(tmp_path):
    from accessories.jsaux_pixel.runtime import Runtime

    def no_io():
        raise AssertionError("no serial io on other machines")

    runtime = Runtime(settings_dir=tmp_path, device_key="rog_ally", log=lambda *a, **k: None,
                      find_panel=no_io, uid=1000)
    runtime.start()
    runtime.service.tick()
    assert runtime.worker is None
    state = runtime.state()
    assert state["supported"] is False and state["present"] is False


def test_unknown_scene_is_an_error_not_a_write(plugin):  # noqa: F811
    before = asyncio.run(plugin.get_accessories_state())["scene"]
    result = asyncio.run(plugin.set_accessory_scene("nope", {}))
    assert result["ok"] is False
    assert asyncio.run(plugin.get_accessories_state())["scene"] == before


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
        return {"scene": "weather", "options": {"city": city, "theme": "aurora"}, "game_options": {},
                "shown_options": {"city": city}, "catalog": [1]}

    monkeypatch.setattr(plugin, "get_accessories_state", state)
    report = asyncio.run(plugin._accessories_report_state())
    assert report["options"] == {"city": True, "theme": "aurora"}
    assert report["shown_options"] == {"city": True}
    assert "catalog" not in report
    assert "Sevilla" not in repr(report)
