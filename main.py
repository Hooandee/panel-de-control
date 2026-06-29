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
from fans.hwmon import FanReader

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
        self._fan_reader = FanReader()
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

    # ---- Fans (read-only monitor) ------------------------------------------
    async def get_fan_state(self) -> dict:
        self._init()
        return self._fan_reader.read()

    # ---- TDP helpers + RPCs -------------------------------------------------
    def _clamp_levels(self, eff: dict) -> dict:
        lim = self._tdp_backend.get_limits()
        ll = self._tdp_backend.level_limits()

        def clamp(value, key):
            b = ll.get(key)
            lo = b["min"] if b else lim.min_w
            hi = b["max"] if b else lim.max_ac_w
            return max(lo, min(int(value), hi))

        return {"pl1": clamp(eff["pl1"], "pl1"),
                "pl2": clamp(eff["pl2"], "pl2"),
                "pl3": clamp(eff["pl3"], "pl3")}

    def _reapply_tdp(self, on_ac=None):
        self._init()
        eff = self._tdp_profiles.effective(self._current_appid)
        ac = read_on_ac() if on_ac is None else on_ac
        return self._tdp_backend.set_levels(eff["pl1"], eff["pl2"], eff["pl3"], ac)

    async def get_tdp_state(self) -> dict:
        self._init()
        limits = self._tdp_backend.get_limits()
        ll = self._tdp_backend.level_limits()
        eff = self._tdp_profiles.effective(self._current_appid)
        geff = self._tdp_profiles.effective(None)
        return {
            "supported": self._tdp_backend.supported,
            "backend": self._tdp_backend.name,
            "limits": {"min": limits.min_w, "default": limits.default_w,
                       "max": limits.max_w, "max_ac": limits.max_ac_w},
            "on_ac": read_on_ac(),
            "appid": self._current_appid,
            "has_game_profile": (self._current_appid is not None
                                 and self._tdp_profiles.has_game(self._current_appid)),
            "watts": limits.clamp(eff["watts"]),
            "global_watts": limits.clamp(geff["watts"]),
            "applied_w": self._tdp_backend.read_applied(),
            "supports_advanced": ("pl2" in ll or "pl3" in ll),
            "level_limits": ll,
            "levels": self._clamp_levels(eff),
            "auto": eff["auto"],
            "global_levels": self._clamp_levels(geff),
            "global_auto": geff["auto"],
        }

    def _resolve_scope(self, scope, appid):
        """Normalize scope/appid; returns scope or None if invalid."""
        if scope not in ("global", "game"):
            return None
        if scope == "game" and appid is None:
            return "global"
        if scope == "game" and appid is not None:
            self._current_appid = str(appid)
        return scope

    async def set_tdp_watts(self, watts: int, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        clamped = self._tdp_backend.get_limits().clamp(watts)
        self._tdp_profiles.set_pl1(resolved, clamped, appid=appid)
        res = self._reapply_tdp()
        return {"requested_w": res.requested_w, "applied_w": res.applied_w,
                "ok": res.ok, "detail": res.detail}

    async def set_tdp_levels(self, off2: int, off3: int, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": 0, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        self._tdp_profiles.set_offsets(resolved, off2, off3, appid=appid)
        res = self._reapply_tdp()
        # requested_w/applied_w reflect resulting sustained pl1 (readback), not the offsets
        return {"requested_w": res.requested_w, "applied_w": res.applied_w,
                "ok": res.ok, "detail": res.detail}

    async def reset_tdp_auto(self, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": 0, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        self._tdp_profiles.set_auto(resolved, appid=appid)
        res = self._reapply_tdp()
        # requested_w/applied_w reflect resulting sustained pl1 (readback), not the offsets
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
