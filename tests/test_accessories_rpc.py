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
