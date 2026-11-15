import asyncio

from kiosk.rpc import plugin_dispatch


class FakePlugin:
    async def get_tdp_state(self):
        return {"unit": "level"}

    async def set_tdp(self, watts, scope="global"):
        return {"watts": watts, "scope": scope}

    async def _main(self):
        return None

    def sync_helper(self):
        return None


def test_dispatch_passes_positional_args_like_decky():
    dispatch = plugin_dispatch(FakePlugin())
    assert asyncio.run(dispatch("set_tdp", [6, "game"])) == {"watts": 6, "scope": "game"}
