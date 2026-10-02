import asyncio

import pytest

from kiosk.bridge import BridgeError, EVENT, SteamBridge


def test_a_steam_reply_completes_the_call():
    async def run():
        sent = []

        async def emit(*event):
            sent.append(event)
            bridge.resolve(event[1], True, {"value": 0.6})

        bridge = SteamBridge(emit)
        result = await bridge.call("brightness.get", [])
        return sent, result

    sent, result = asyncio.run(run())
    assert sent == [(EVENT, 1, "brightness.get", [])]
    assert result == {"value": 0.6}


def test_steam_failures_surface_as_errors():
    async def run():
        async def emit(_event, request_id, *_):
            bridge.resolve(request_id, False, "no_running_game")

        bridge = SteamBridge(emit)
        await bridge.call("screenshot", [])

    with pytest.raises(BridgeError, match="no_running_game"):
        asyncio.run(run())


def test_no_answer_means_steam_is_unavailable():
    async def run():
        async def emit(*_):
            return None

        bridge = SteamBridge(emit, timeout_s=0.01)
        await bridge.call("keyboard", [])

    with pytest.raises(BridgeError, match="steam_unavailable"):
        asyncio.run(run())


def test_only_listed_actions_reach_steam():
    async def run():
        async def emit(*_):
            raise AssertionError("must not emit")

        await SteamBridge(emit).call("eval", ["alert(1)"])

    with pytest.raises(BridgeError, match="unknown_action"):
        asyncio.run(run())


def test_late_or_unknown_replies_are_ignored():
    bridge = SteamBridge(lambda *_: None)
    assert bridge.resolve(99, True, None) is False
