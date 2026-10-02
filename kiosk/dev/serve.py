"""Development only: serve dist/kiosk against a real Plugin on this machine (never packaged)."""

import asyncio
import logging
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "py_modules")]

decky = types.ModuleType("decky")
decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="pdc-kiosk-dev-")
decky.DECKY_PLUGIN_DIR = str(ROOT)
decky.DECKY_USER = "deck"
decky.logger = logging.getLogger("pdc-kiosk-dev")
sys.modules["decky"] = decky
logging.basicConfig(level=logging.INFO)

import main  # noqa: E402
from kiosk.rpc import plugin_dispatch, public_rpc_methods  # noqa: E402
from kiosk.server import KioskServer  # noqa: E402


async def run() -> None:
    plugin = main.Plugin()
    plugin._init()
    server = KioskServer(
        str(ROOT / "dist" / "kiosk"),
        plugin_dispatch(plugin),
        public_rpc_methods(plugin),
        on_error=lambda method, error: decky.logger.warning("rpc %s failed: %s", method, error),
    )
    await server.start()
    print(server.url, flush=True)
    await asyncio.Event().wait()


asyncio.run(run())
