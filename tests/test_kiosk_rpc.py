import asyncio
import re
from pathlib import Path

from kiosk.rpc import KIOSK_RPC_METHODS, kiosk_rpc_methods, plugin_dispatch

NATIVE = Path(__file__).resolve().parents[1] / "py_modules" / "kiosk" / "native"


class FakePlugin:
    async def get_kiosk_vitals(self):
        return {"watts": 8.7}

    async def set_kiosk_brightness(self, value, save=True):
        return {"value": value, "save": save}

    async def set_remote_access_enabled(self, enabled):
        return {"enabled": enabled}

    async def _main(self):
        return None

    def get_battery_state(self):
        return None


def test_exposes_only_listed_coroutines_the_plugin_has():
    assert kiosk_rpc_methods(FakePlugin()) == {"get_kiosk_vitals", "set_kiosk_brightness"}


def test_developer_and_remote_access_methods_never_reach_the_kiosk():
    sensitive = {
        "set_developer_options", "set_remote_access_enabled", "open_remote_access_pairing",
        "close_remote_access_pairing", "answer_remote_access_pairing", "forget_remote_access_keys",
    }
    assert not sensitive & KIOSK_RPC_METHODS


def _native_calls() -> set[str]:
    source = "\n".join(path.read_text(encoding="utf-8") for path in NATIVE.glob("*.py"))
    calls = set(re.findall(r'worker\.act\(\s*[^,]+,\s*"([a-z_]+)"', source))
    calls |= set(re.findall(r'worker\.latest\(\s*[^,]+,\s*[A-Z_]+,\s*[^,]+,\s*"([a-z_]+)"', source))
    calls |= set(re.findall(r'_call\("[^"]*",\s*"([a-z_]+)"', source))
    calls |= set(re.findall(r'\("[a-z_]+",\s*"((?:get|set)_[a-z_]+)"\)', source))
    calls |= set(re.findall(r'"[a-z_]+":\s*\("((?:get|set|kiosk)_[a-z_]+)"', source))
    return calls


def test_every_method_the_native_kiosk_calls_is_listed():
    calls = _native_calls()
    assert {"get_kiosk_vitals", "kiosk_steam", "set_fan_preset", "get_ui_prefs"} <= calls
    assert calls <= KIOSK_RPC_METHODS


def test_dispatch_passes_positional_args_like_decky():
    dispatch = plugin_dispatch(FakePlugin())
    assert asyncio.run(dispatch("set_kiosk_brightness", [0.4, False])) == {"value": 0.4, "save": False}
