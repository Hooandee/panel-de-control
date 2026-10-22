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
