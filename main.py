import os
from dataclasses import asdict

import decky

# py_modules/ is on sys.path → import TOP-LEVEL (never `from py_modules.x import`).
import device_registry
from version import read_version
from settings_store import SettingsStore

DEFAULTS = {
    "enabled": True,
    # add your settings keys here; SettingsStore merges these over stored values
}


class Plugin:
    # Lazy, idempotent init called at the top of EVERY RPC method and _main.
    # RPC can be invoked before _main finishes; without this, methods AttributeError
    # on a half-built instance and the UI hangs on its spinner.
    def _init(self) -> None:
        if getattr(self, "_ready", False):
            return
        self._store = SettingsStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "state.json")
        )
        self._settings = self._store.load(DEFAULTS)
        # Probe hardware/environment HERE, wrapped so it NEVER raises — a raise in
        # init or _main bricks plugin load (UI stuck on spinner forever).
        self._device = device_registry.detect()
        self._ready = True

    def _save(self) -> None:
        self._store.save(self._settings)

    # ---- RPC methods (referenced by name from src/api.ts) -------------------
    async def get_version(self) -> str:
        self._init()
        return read_version()

    async def get_state(self) -> dict:
        self._init()
        return dict(self._settings)

    async def set_enabled(self, on: bool) -> None:
        self._init()
        self._settings["enabled"] = on
        self._save()
        # apply the change to hardware/effect here

    async def get_device(self) -> dict:
        self._init()
        return asdict(self._device)

    # ---- lifecycle ----------------------------------------------------------
    async def _main(self) -> None:
        self._init()
        decky.logger.info(
            "Panel de Control v%s loaded (euid=%s)", read_version(), os.geteuid()
        )

    async def _unload(self) -> None:
        # cancel asyncio tasks, stop loops, release hardware here
        decky.logger.info("Panel de Control unloaded")

    async def _uninstall(self) -> None:
        decky.logger.info("Panel de Control uninstalled")
