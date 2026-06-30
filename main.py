import asyncio
import os
from dataclasses import asdict

import decky

# py_modules/ is on sys.path → import TOP-LEVEL (never `from py_modules.x import`).
import auto_tdp
import device_registry
from version import read_version
from settings_store import SettingsStore
from tdp import factory as tdp_factory
from tdp_profiles import ProfileStore
from lifecycle import LifecycleManager, read_on_ac
from fans.hwmon import FanReader, extract_cpu_gpu_temps
from fans import control as fan_control
from fans import presets as fan_presets
from fan_curves import FanCurveStore
from power.reader import PowerReader
from telemetry.store import TelemetryStore
from telemetry.sampler import TelemetrySampler

DEFAULTS = {
    # Persisted settings keys go here; SettingsStore merges these over stored values.
    # (TDP per-game profiles will live in their own store in the TDP sub-project.)
    "auto_tdp": False,
    # Learn from usage (local-only telemetry powering F3 suggestions). Opt-out:
    # when False the sampler never runs — nothing is read or written during play.
    "telemetry_enabled": True,
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
        self._fan_ctrl = fan_control.select_fan_backend(self._device)
        self._fan_curves = FanCurveStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "fan_curves.json")
        )
        self._power_reader = PowerReader()
        self._current_appid = None
        self._lifecycle = LifecycleManager(apply_cb=self._reapply_all)
        self._auto_task = None
        self._auto_setpoint = None
        self._telemetry = TelemetryStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "telemetry.json")
        )
        self._sampler = TelemetrySampler(self._telemetry, self._collect_sample)
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

    # ---- Fan-curve control (global + per-game, persisted) -------------------
    def _reapply_fans(self) -> None:
        """Apply the effective fan profile for the current game (or global).

        auto -> firmware control; manual -> write the stored curve to all fans.
        Guarded: a bad fan apply must never brick load.
        """
        try:
            profile = self._fan_curves.effective(self._current_appid)
            if profile["preset"] == "auto" or not profile["points"]:
                self._fan_ctrl.set_auto(None)
            else:
                self._fan_ctrl.apply_curve_all(profile["points"])
        except Exception:  # noqa: BLE001
            pass

    def _fan_curve_state(self) -> dict:
        hw_state = self._fan_ctrl.read_state()
        effective = self._fan_curves.effective(self._current_appid)
        # When idle (no game) the effective profile IS the global one — skip the
        # second store read.
        global_curve = effective if self._current_appid is None else self._fan_curves.effective(None)
        return {
            "supported": hw_state.get("supported", False),
            "source": hw_state.get("source"),
            "pwm_max": hw_state.get("pwm_max", 255),
            "preset": effective["preset"],
            "points": effective["points"],
            "global_preset": global_curve["preset"],
            "global_points": global_curve["points"],
            "has_game_profile": (self._current_appid is not None
                                 and self._fan_curves.has_game(self._current_appid)),
            "appid": self._current_appid,
            "presets": [{"id": pid, "points": pts}
                        for pid, pts in fan_presets.RESOLVED.items()],
        }

    async def get_fan_curve_state(self) -> dict:
        self._init()
        return self._fan_curve_state()

    async def set_fan_preset(self, preset: str, scope: str, appid=None) -> dict:
        self._init()
        if preset not in fan_presets.PRESETS:
            return self._fan_curve_state()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return self._fan_curve_state()
        self._fan_curves.set_preset(resolved, preset, fan_presets.RESOLVED[preset], appid)
        self._reapply_fans()
        return self._fan_curve_state()

    async def set_fan_curve_points(self, points: list, scope: str, appid=None) -> dict:
        self._init()
        if not isinstance(points, list) or not points:
            return self._fan_curve_state()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return self._fan_curve_state()
        # Store the SANITIZED curve (8 points, monotonic, hot-point safety floor) —
        # the same transform applied at write time — so the persisted/returned state
        # reflects what the hardware will actually run. Never show a curve we override.
        safe_points = [list(p) for p in fan_control.sanitize_curve(points)]
        self._fan_curves.set_custom(resolved, safe_points, appid)
        self._reapply_fans()
        return self._fan_curve_state()

    async def set_fan_auto(self, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return self._fan_curve_state()
        self._fan_curves.set_auto(resolved, appid)
        self._reapply_fans()
        return self._fan_curve_state()

    # ---- Telemetry ----------------------------------------------------------
    def _collect_sample(self):
        """Build one telemetry sample from live readers.

        Returns (appid, sample_dict) while in-game, or None when idle.
        Never raises; any error degrades to None (no sample recorded).
        """
        try:
            if self._current_appid is None:
                return None

            pr = self._power_reader.read()
            fan = self._fan_reader.read()

            # CPU / GPU temps — prefer labels "CPU" / "GPU", fall back to position
            temp_cpu, temp_gpu = extract_cpu_gpu_temps(fan)

            # Max RPM across all fans (None if no fans)
            fans = fan.get("fans") or []
            fan_rpms = [f["rpm"] for f in fans if f.get("rpm") is not None]
            fan_rpm = max(fan_rpms) if fan_rpms else None

            # Clamped effective setpoint (mirrors get_power_draw)
            pl1 = self._effective_levels(self._current_appid)[0]["pl1"]

            sample = {
                "pl1": pl1,
                "watts": pr.get("watts"),
                "gpu_busy": pr.get("gpu_busy"),
                "temp_cpu": temp_cpu,
                "temp_gpu": temp_gpu,
                "fan_rpm": fan_rpm,
            }
            return (self._current_appid, sample)
        except Exception:  # noqa: BLE001
            return None

    async def get_telemetry(self, appid=None) -> dict:
        self._init()
        key = str(appid) if appid is not None else self._current_appid
        if key is None:
            return {"samples_n": 0, "by_pl1": {}, "recent": []}
        return self._telemetry.aggregate(key)

    async def get_telemetry_enabled(self) -> bool:
        self._init()
        return bool(self._settings.get("telemetry_enabled", True))

    async def set_telemetry_enabled(self, enabled: bool) -> bool:
        """Opt out of (or back into) usage learning. Off stops the sampler so
        nothing is read or written during play; on resumes it."""
        self._init()
        enabled = bool(enabled)
        self._settings["telemetry_enabled"] = enabled
        self._save()
        if enabled:
            self._sampler.start()
        else:
            self._sampler.stop()  # also flushes any buffered samples
        return enabled

    # ---- Auto-TDP loop ------------------------------------------------------
    def _start_auto_loop(self) -> None:
        if self._auto_task is not None and not self._auto_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop in tests — skip task creation safely
        self._auto_task = asyncio.create_task(self._auto_loop())

    def _stop_auto_loop(self) -> None:
        if self._auto_task is not None:
            self._auto_task.cancel()
            self._auto_task = None

    async def _auto_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(2)
                pr = self._power_reader.read()
                gpu_busy = pr.get("gpu_busy")
                levels, active, _ac = self._effective_levels(self._current_appid)
                cur = levels["pl1"]
                limits = self._tdp_backend.get_limits()
                nxt = auto_tdp.decide(cur, gpu_busy, limits.min_w, active)
                if nxt != cur:
                    scope = "game" if self._current_appid else "global"
                    self._tdp_profiles.set_pl1(scope, nxt, appid=self._current_appid)
                    self._reapply_tdp()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                pass  # loop must never die

    # ---- Power draw + auto-TDP RPCs -----------------------------------------
    async def get_power_draw(self) -> dict:
        self._init()
        pr = self._power_reader.read()
        auto = bool(self._settings.get("auto_tdp"))
        setpoint = self._effective_levels(self._current_appid)[0]["pl1"]
        return {
            "watts": pr["watts"],
            "gpu_busy": pr["gpu_busy"],
            "auto_tdp": auto,
            "setpoint": setpoint,
        }

    async def set_auto_tdp(self, enabled: bool) -> dict:
        self._init()
        self._settings["auto_tdp"] = bool(enabled)
        self._save()
        if enabled:
            self._start_auto_loop()
        else:
            self._stop_auto_loop()
        return {"auto_tdp": bool(enabled)}

    # ---- TDP helpers + RPCs -------------------------------------------------
    def _effective_levels(self, appid=None, on_ac=None):
        """Clamped {pl1,pl2,pl3} for a scope at the active (on_ac) ceiling, plus the
        ceiling. Single source for every loop/RPC that needs the applied setpoint."""
        limits = self._tdp_backend.get_limits()
        ac = read_on_ac() if on_ac is None else on_ac
        active = self._active_max(limits, ac)
        ll = self._cap_level_limits(self._tdp_backend.level_limits(), active)
        levels = self._clamp_levels(self._tdp_profiles.effective(appid), limits, active, ll)
        return levels, active, ac

    def _cap_level_limits(self, ll: dict, active_max: int) -> dict:
        """Cap each rail's max to the active (on_ac) ceiling so the UI never offers
        more than the device can deliver on the current power source."""
        out = {}
        for key, b in ll.items():
            hi = min(b["max"], active_max)
            out[key] = {"min": min(b["min"], hi), "max": hi}
        return out

    def _clamp_levels(self, eff: dict, lim, active_max: int, ll: dict) -> dict:
        def clamp(value, key):
            b = ll.get(key)
            lo = b["min"] if b else lim.min_w
            hi = b["max"] if b else active_max
            return max(lo, min(int(value), hi))

        return {"pl1": clamp(eff["pl1"], "pl1"),
                "pl2": clamp(eff["pl2"], "pl2"),
                "pl3": clamp(eff["pl3"], "pl3")}

    def _active_max(self, limits, ac: bool) -> int:
        return limits.max_ac_w if ac else limits.max_w

    def _reapply_tdp(self, on_ac=None):
        self._init()
        lv, _active, ac = self._effective_levels(self._current_appid, on_ac)
        return self._tdp_backend.set_levels(lv["pl1"], lv["pl2"], lv["pl3"], ac)

    def _reapply_all(self, on_ac=None) -> None:
        """Lifecycle callback: re-assert TDP and the effective fan curve (resume/AC)."""
        self._reapply_tdp(on_ac)
        self._reapply_fans()

    async def get_tdp_state(self) -> dict:
        self._init()
        levels, active, ac = self._effective_levels(self._current_appid)
        global_levels, _active, _ac = self._effective_levels(None, ac)
        limits = self._tdp_backend.get_limits()
        ll = self._cap_level_limits(self._tdp_backend.level_limits(), active)
        eff = self._tdp_profiles.effective(self._current_appid)
        geff = self._tdp_profiles.effective(None)
        return {
            "supported": self._tdp_backend.supported,
            "backend": self._tdp_backend.name,
            "limits": {"min": limits.min_w, "default": limits.default_w,
                       "max": limits.max_w, "max_ac": limits.max_ac_w},
            "on_ac": ac,
            "appid": self._current_appid,
            "has_game_profile": (self._current_appid is not None
                                 and self._tdp_profiles.has_game(self._current_appid)),
            "watts": limits.clamp(eff["watts"], ac),
            "global_watts": limits.clamp(geff["watts"], ac),
            "applied_w": self._tdp_backend.read_applied(),
            "supports_advanced": ("pl2" in ll or "pl3" in ll),
            "level_limits": ll,
            "levels": levels,
            "auto": eff["auto"],
            "global_levels": global_levels,
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
        limits = self._tdp_backend.get_limits()
        clamped = limits.clamp(watts, read_on_ac())
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
        self._reapply_all()
        return await self.get_tdp_state()

    def _restore_fans_safe(self) -> None:
        try:
            if getattr(self, "_fan_ctrl", None) is not None:
                self._fan_ctrl.restore_auto()
        except Exception:  # noqa: BLE001
            pass

    # ---- lifecycle ----------------------------------------------------------
    async def _main(self) -> None:
        self._init()
        decky.logger.info(
            "Panel de Control v%s loaded (euid=%s)", read_version(), os.geteuid()
        )
        try:
            self._reapply_all()
            self._lifecycle.start()
            if self._settings.get("auto_tdp"):
                self._start_auto_loop()
            if self._settings.get("telemetry_enabled", True):
                self._sampler.start()
        except Exception as e:  # noqa: BLE001
            decky.logger.error("TDP startup failed: %s", e)

    async def _unload(self) -> None:
        # Restore fans to firmware auto FIRST — before stopping other loops —
        # so the hardware is never left with a stale manual curve.
        self._restore_fans_safe()
        self._stop_auto_loop()
        if getattr(self, "_sampler", None) is not None:
            self._sampler.stop()
        if getattr(self, "_lifecycle", None) is not None:
            self._lifecycle.stop()
        decky.logger.info("Panel de Control unloaded")

    async def _uninstall(self) -> None:
        self._restore_fans_safe()
        decky.logger.info("Panel de Control uninstalled")
