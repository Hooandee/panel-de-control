import os
from dataclasses import asdict

import decky

# py_modules/ is on sys.path → import TOP-LEVEL (never `from py_modules.x import`).
import device_registry
from version import read_version
from settings_store import SettingsStore
from tdp import factory as tdp_factory
from tdp_profiles import ProfileStore
from lifecycle import LifecycleManager, read_on_ac

DEFAULTS = {
    # Persisted settings keys go here; SettingsStore merges these over stored values.
    # (TDP per-game profiles will live in their own store in the TDP sub-project.)
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
        self._tdp_profiles = ProfileStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "tdp_profiles.json"),
            default_watts=self._device.tdp_default or 15,
        )
        self._tdp_backend = tdp_factory.select_backend(self._device)
        self._current_appid = None
        self._lifecycle = LifecycleManager(apply_cb=self._reapply_tdp)
        self._ready = True

    def _save(self) -> None:
        self._store.save(self._settings)

    # ---- RPC methods (referenced by name from src/api.ts) -------------------
    async def get_version(self) -> str:
        self._init()
        return read_version()

    async def get_device(self) -> dict:
        self._init()
        return asdict(self._device)

    # ---- TDP helpers + RPCs -------------------------------------------------
    def _reapply_tdp(self, on_ac=None):
        self._init()
        prof = self._tdp_profiles.effective(self._current_appid)
        limits = self._tdp_backend.get_limits()
        watts = limits.clamp(prof["watts"])
        ac = read_on_ac() if on_ac is None else on_ac
        return self._tdp_backend.set_tdp(watts, ac)

    async def get_tdp_state(self) -> dict:
        self._init()
        limits = self._tdp_backend.get_limits()
        prof = self._tdp_profiles.effective(self._current_appid)
        return {
            "supported": self._tdp_backend.supported,
            "backend": self._tdp_backend.name,
            "limits": {"min": limits.min_w, "default": limits.default_w,
                       "max": limits.max_w, "max_ac": limits.max_ac_w},
            "on_ac": read_on_ac(),
            "appid": self._current_appid,
            "has_game_profile": (self._current_appid is not None
                                 and self._tdp_profiles.has_game(self._current_appid)),
            "watts": limits.clamp(prof["watts"]),
            "global_watts": limits.clamp(self._tdp_profiles.effective(None)["watts"]),
            "applied_w": self._tdp_backend.read_applied(),
        }

    async def set_tdp_watts(self, watts: int, scope: str, appid=None) -> dict:
        self._init()
        if scope not in ("global", "game"):
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        if scope == "game" and appid is None:
            scope = "global"
        clamped = self._tdp_backend.get_limits().clamp(watts)
        if scope == "game" and appid is not None:
            self._current_appid = str(appid)
        self._tdp_profiles.set_watts(scope, clamped, appid=appid)
        res = self._reapply_tdp()
        return {"requested_w": res.requested_w, "applied_w": res.applied_w,
                "ok": res.ok, "detail": res.detail}

    async def create_game_profile(self, appid) -> None:
        self._init()
        self._tdp_profiles.create_game_from_global(appid)
        self._current_appid = str(appid)

    async def set_current_game(self, appid) -> dict:
        self._init()
        self._current_appid = str(appid) if appid is not None else None
        self._reapply_tdp()
        return await self.get_tdp_state()

    # ---- lifecycle ----------------------------------------------------------
    async def _main(self) -> None:
        self._init()
        decky.logger.info(
            "Panel de Control v%s loaded (euid=%s)", read_version(), os.geteuid()
        )
        try:
            self._reapply_tdp()
            self._lifecycle.start()
        except Exception as e:  # noqa: BLE001
            decky.logger.error("TDP startup failed: %s", e)

    async def _unload(self) -> None:
        # cancel asyncio tasks, stop loops, release hardware here
        if getattr(self, "_lifecycle", None) is not None:
            self._lifecycle.stop()
        decky.logger.info("Panel de Control unloaded")

    async def _uninstall(self) -> None:
        decky.logger.info("Panel de Control uninstalled")
