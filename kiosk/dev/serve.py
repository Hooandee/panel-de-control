"""Development only: serve dist/kiosk against a real Plugin on this machine (never packaged)."""

import asyncio
import logging
import math
import os
import sys
import time
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


DEMO_GAME = os.environ.get("PDC_KIOSK_DEMO_GAME", "413150")
DEMO_ART = os.environ.get("PDC_KIOSK_DEMO_ART", "")


def demo_reading(name: str, real):
    """Moving fake readings so the layout and its animations can be judged without hardware."""
    wave = (math.sin(time.time() / 4) + 1) / 2
    if name == "get_power_draw":
        return {"watts": round(6 + 5 * wave, 1), "gpu_busy": round(35 + 50 * wave), "auto_tdp": True,
                "setpoint": None, "applied": None, "on_ac": False, "ownership": {},
                "auto": {"state": "holding", "reason": "", "setpoint": None, "fps": round(57 + 3 * wave),
                         "target_fps": 60, "signal_age_s": 0, "focus": None, "seed_source": None,
                         "seed_watts": None, "held_watts": None}}
    if name == "get_battery_state":
        return {"battery": {"present": True, "percent": 64, "status": "Discharging", "health_percent": 98,
                            "cycle_count": 12, "energy_now_mwh": None, "energy_full_mwh": None,
                            "energy_full_design_mwh": None, "power_now_w": 7.4, "eta_seconds": 11520,
                            "ac_online": False}, "charge_limit": {"supported": False}}
    if name == "get_fan_state":
        return {"supported": True, "fans": [{"label": "Fan", "rpm": int(1900 + 900 * wave), "percent": 50}],
                "temps": [{"label": "CPU", "celsius": round(55 + 14 * wave, 1)}, {"label": "GPU", "celsius": 58}]}
    if name == "get_tdp_state":
        return {**real, "unit": "level", "appid": DEMO_GAME or None}
    if name == "get_kiosk_game":
        return {"appid": DEMO_GAME, "name": "Stardew Valley"}
    return real


def demo_dispatch(dispatch):
    async def wrapped(name, args):
        try:
            real = await dispatch(name, args)
        except Exception:  # noqa: BLE001
            real = {}
        return demo_reading(name, real)

    return wrapped


async def run() -> None:
    plugin = main.Plugin()
    plugin._init()
    demo = "--demo" in sys.argv
    dispatch = plugin_dispatch(plugin)
    server = KioskServer(
        str(ROOT / "dist" / "kiosk"),
        demo_dispatch(dispatch) if demo else dispatch,
        public_rpc_methods(plugin),
        on_error=lambda method, error: decky.logger.warning("rpc %s failed: %s", method, error),
        art=(lambda appid, kind: (os.path.join(DEMO_ART, "hero.jpg"), "image/jpeg")
             if demo and DEMO_ART and kind == "hero" else None),
    )
    await server.start()
    print(server.url, flush=True)
    await asyncio.Event().wait()


asyncio.run(run())
