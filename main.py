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
from tdp import suggest as tdp_suggest
from tdp_profiles import ProfileStore
from lifecycle import LifecycleManager, read_on_ac
from fans.hwmon import FanReader, extract_cpu_gpu_temps
from fans import control as fan_control
from fans import presets as fan_presets
from fans import suggest as fan_suggest
from fan_curves import FanCurveStore
from power.reader import PowerReader
from battery.reader import BatteryReader
from battery.charge_limit import select_charge_limit
from cpu.info import read_cpu_info, read_cpu_model
from cpu.controls import SmtControl, select_boost
from telemetry.store import TelemetryStore
from telemetry.sampler import TelemetrySampler

# Auto-TDP rolling window: last N samples (~2 s apart) the control law reads. It
# measures the FREQUENCY of boost over the window (not an instant), so it is longer
# than the old reactive window; the up-trigger still uses the recent peak to reject
# transient dips. See py_modules/auto_tdp.py.
_AUTO_WINDOW = 10

DEFAULTS = {
    # Persisted settings keys go here; SettingsStore merges these over stored values.
    # (TDP per-game profiles will live in their own store in the TDP sub-project.)
    "auto_tdp": False,
    # Learn from usage (local-only telemetry powering F3 suggestions). Opt-out:
    # when False the sampler never runs — nothing is read or written during play.
    "telemetry_enabled": True,
    # Opt-in: raise the on-battery TDP ceiling to the firmware/charger max. Default
    # off (we cap battery below the firmware max for battery life); the user accepts
    # the drain when enabling. The firmware itself allows the same max either way.
    "unlock_battery_max": False,
    # Opt-in: while the QAM/plugin UI is open, raise PL1 to a responsive floor so the
    # CPU-bound menu render stays fluid. Default OFF for honesty — raising TDP behind
    # the menu would show an inflated number vs the REAL in-game TDP the user wants to
    # see with the QAM open. When ON, the user accepts the menu-time bump for fluidity.
    "qam_tdp_boost": False,
    # Battery charge limit: when enabled, cap charging at `charge_limit_percent`
    # (protects battery longevity). Disabled → firmware default (100%).
    "charge_limit_enabled": False,
    "charge_limit_percent": 80,
    # CPU controls default to full performance (SMT + boost on) — the stock state.
    "smt_enabled": True,
    "boost_enabled": True,
    # Download mode (low power while a game downloads unattended): TDP→min, boost
    # off, ambient screen dim. `eco_brightness` = the pre-eco brightness % to wake
    # back to. Both restored/derived on exit; eco_enabled is a pure override.
    "eco_enabled": False,
    "eco_brightness": 40,
}


class Plugin:
    # A1: re-fit + re-apply the learned fan curve every this-many collected in-game
    # samples. The sampler ticks every 5 s only while in-game, so 360 × 5 s ≈ 30 min
    # of ACTUAL play — matching the telemetry histogram's ~30 min decay half-life so
    # the curve tracks the current thermal "zone" without explicit zone detection.
    _REAPPLY_EVERY_TICKS = 360

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
        # temp_fn feeds the software-loop backends (Steam Deck / Legion Go 2) the
        # live driving temp; hardware-curve backends (ASUS/MSI) ignore it.
        self._fan_ctrl = fan_control.select_fan_backend(self._device, temp_fn=self._driving_temp)
        self._fan_curves = FanCurveStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "fan_curves.json")
        )
        self._power_reader = PowerReader()
        self._battery = BatteryReader()
        self._charge_limit = select_charge_limit(self._device)
        self._smt = SmtControl()
        self._boost = select_boost()
        # Topology + freq range are static — read once (only SMT/boost state is live).
        self._cpu_info = read_cpu_info()
        # Real silicon name (static) shown in the DeviceHeader instead of the hardcoded
        # table chip; read once here like _cpu_info. None on generic or when unreadable.
        self._chip = read_cpu_model() if not self._device.is_generic else None
        self._current_appid = None
        self._lifecycle = LifecycleManager(apply_cb=self._reapply_all)
        self._auto_task = None
        self._auto_setpoint = None
        # Rolling GPU% window + slack counter for the GPU-driven auto-TDP control law.
        self._gpu_window = []      # recent GPU% samples
        self._slack_ticks = 0      # consecutive GPU-headroom ticks (temporal gate)
        # QAM/plugin UI open → the auto loop uses a higher "responsive" floor so the
        # CPU-bound menu render stays fluid (the GPU-only loop can't see CPU load).
        # Set/cleared by the ControlCenter mount/unmount via set_ui_active.
        self._ui_active = False
        self._telemetry = TelemetryStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "telemetry.json")
        )
        # A1: count in-game samples toward the periodic adaptive re-fit.
        self._reapply_ticks = 0
        # Whether the adaptive curve has been driven THIS session (per game). Lets the
        # mid-session drive fire the moment `enough_data` flips true instead of waiting
        # for the next ~30 min re-fit. Reset on game change (and on sampler (re)start).
        self._adaptive_applied = False
        # Last adaptive curve actually driven to hardware — the anti-churn baseline for
        # the periodic re-fit (adaptive stores no points, so we track it here).
        self._last_adaptive_points = None
        self._sampler = TelemetrySampler(
            self._telemetry, self._collect_sample, on_sample=self._on_sample_collected
        )
        self._ready = True

    def _save(self) -> None:
        self._store.save(self._settings)

    # ---- RPC methods (referenced by name from src/api.ts) -------------------
    async def get_version(self) -> str:
        self._init()
        return read_version()

    async def get_device(self) -> dict:
        self._init()
        d = asdict(self._device)
        # Show the REAL silicon name (cached in _init) rather than the hardcoded table
        # value, which can drift per unit/variant (e.g. Legion Go 2 = "Ryzen Z2
        # Extreme", not the Ally X's "Ryzen AI Z2 Extreme"). Falls back to the table
        # chip when the kernel exposes nothing.
        if self._chip:
            d["chip"] = self._chip
        return d

    # ---- Fans (read-only monitor) ------------------------------------------
    def _read_fans(self) -> dict:
        """hwmon fan/temp reading, with EC-readable RPM merged in for devices that
        expose NO hwmon fan (Legion Go 2 reads RPM over the EC). Shared by the
        monitor RPC and the telemetry sampler so both see the real RPM, not an empty
        list. Honest: a value only appears when actually readable. Never raises."""
        state = self._fan_reader.read()
        if not state["fans"]:
            try:
                hw = self._fan_ctrl.read_state()
                ec_fans = [{"label": f.get("key", "fan"), "rpm": rpm, "percent": None}
                           for f in hw.get("fans", []) if (rpm := f.get("rpm")) is not None]
                if ec_fans:
                    state = {**state, "supported": True, "fans": ec_fans}
            except Exception:  # noqa: BLE001
                pass
        return state

    async def get_fan_state(self) -> dict:
        self._init()
        return self._read_fans()

    def _driving_temp(self):
        """Live driving temperature (max of CPU/GPU) for software-loop backends.
        Never raises; returns None if no temp is readable."""
        try:
            cpu, gpu = extract_cpu_gpu_temps(self._fan_reader.read())
            vals = [t for t in (cpu, gpu) if t is not None]
            return max(vals) if vals else None
        except Exception:  # noqa: BLE001
            return None

    # ---- Fan-curve control (global + per-game, persisted) -------------------
    def _reapply_fans(self) -> None:
        """Apply the effective fan profile for the current game (or global).

        - auto      -> firmware control.
        - adaptive  -> drive the LEARNED curve (computed live from telemetry): the
                       balanced fit biased by the scope's silence↔cool dial. When
                       there isn't enough real data yet, fall back to firmware auto
                       (never fabricate a curve) — the card shows the learning state.
        - preset/custom -> write the stored 8-point curve to all fans.
        Guarded: a bad fan apply must never brick load.
        """
        try:
            profile = self._fan_curves.effective(self._current_appid)
            preset = profile["preset"]
            if preset == "adaptive":
                points = self._adaptive_curve_points(self._current_appid)
                if points is None:
                    self._fan_ctrl.set_auto(None)  # not enough data → honest firmware auto
                else:
                    self._fan_ctrl.apply_curve_all(points)
            elif preset == "auto" or not profile["points"]:
                self._fan_ctrl.set_auto(None)
            else:
                self._fan_ctrl.apply_curve_all(profile["points"])
        except Exception:  # noqa: BLE001
            pass

    def _adaptive_curve_points(self, appid):
        """The learned curve to drive in adaptive mode for *appid* (or None if there
        isn't enough real data yet). Balanced fit biased by the scope's silence↔cool
        dial, sanitized. Never raises; never fabricates a curve without data."""
        sugg = self._fan_suggestion(appid)
        if not sugg["available"] or not sugg["curves"]:
            return None
        bias = self._fan_curves.adaptive_bias(appid)
        pts = fan_suggest.biased_curve(sugg["curves"], bias)
        return [list(p) for p in pts]

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
            "bias": effective.get("bias", 0),
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

    async def set_fan_adaptive(self, scope: str, appid=None) -> dict:
        """Select the Adaptive (learned) curve mode. Choosing this IS the opt-in to
        auto-learning for this scope: the learner now drives + re-fits the curve."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return self._fan_curve_state()
        self._fan_curves.set_adaptive(resolved, appid)
        # Re-arm the mid-session drive, then drive the learned curve now (also sets the
        # anti-churn baseline so the periodic re-fit doesn't needlessly re-drive).
        self._adaptive_applied = False
        self._last_adaptive_points = None
        self._maybe_drive_adaptive_fan_curve()
        self._reapply_fans()  # covers the no-data case (firmware auto) honestly
        return self._fan_curve_state()

    async def set_fan_adaptive_bias(self, bias: int, scope: str, appid=None) -> dict:
        """Set the silence↔cool bias of the Adaptive mode (also selects it). Drives
        the biased learned curve so the hardware reflects the dial immediately."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return self._fan_curve_state()
        self._fan_curves.set_adaptive_bias(resolved, bias, appid)
        # A new bias changes the target curve → reset the anti-churn baseline and drive.
        self._last_adaptive_points = None
        self._maybe_drive_adaptive_fan_curve()
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

    # ---- Fan-curve suggestion (F3 brain over local telemetry) ---------------
    def _fan_suggestion(self, appid=None) -> dict:
        """Suggest a fan curve fit to a game's observed temperature band (sync core).

        Per-game only (the band is learned per game). Degrades honestly:
        - telemetry opted out  -> available False, reason "disabled"
        - device can't write    -> available False, reason "unsupported"
        - not enough/varied data -> available False, reason from enough_data
        Never raises. Shared by the RPC and the proactive auto-apply path.
        """
        key = str(appid) if appid is not None else self._current_appid

        def unavail(reason):
            return {"available": False, "curves": None, "band": None,
                    "minutes": 0, "seconds": 0, "reason": reason,
                    "target_minutes": fan_suggest.MIN_MINUTES,
                    "target_seconds": fan_suggest._MIN_SECONDS}

        # Device-can't-write is checked first: an unsupported device returns
        # "unsupported" (card stays silent) rather than nudging "turn on learning".
        if not self._fan_ctrl.supported:  # cheap property — no sysfs/EC read
            return unavail("unsupported")
        if not bool(self._settings.get("telemetry_enabled", True)):
            return unavail("disabled")
        if key is None:
            return unavail("no_game")
        try:
            hist = self._telemetry.temp_histogram(key)
            total = sum(hist.values()) if hist else 0
            # Floor (not round) so `minutes` can't show the 30-min target while the
            # honest gate is still `too_few` (round(1770/60)=30 would lie). The FE
            # derives the progress bar + "min left" from raw `seconds` anyway.
            minutes = int(total // 60)
            ok, reason = fan_suggest.enough_data(hist)
            # Compute the candidate the moment there's ANY real observed dwell, so the
            # UI can show a live green preview while learning. Gated on total>0 so the
            # no_data verdict never carries a curve (no graph beside "start playing").
            # `available` (=ok) still gates applying — never apply without enough data.
            band = curves = None
            if total > 0:
                band = fan_suggest.band(hist)
                curves = {name: [list(p) for p in pts]
                          for name, pts in fan_suggest.suggest_curves(band).items()}
            return {"available": ok, "reason": reason, "minutes": minutes,
                    "seconds": total, "target_minutes": fan_suggest.MIN_MINUTES,
                    "target_seconds": fan_suggest._MIN_SECONDS, "band": band, "curves": curves}
        except Exception:  # noqa: BLE001
            return unavail("error")

    async def get_fan_suggestion(self, appid=None) -> dict:
        self._init()
        return self._fan_suggestion(appid)

    def _drive_adaptive_fan_curve(self, *, reapply: bool) -> None:
        """Drive the learned curve when the effective mode is Adaptive (never-fake).

        Adaptive is a stateless MODE — it stores no points; the curve is computed
        live from telemetry here. Choosing the mode IS the opt-in, so the only guards
        are: a game is running and the effective curve is Adaptive. Never overrides a
        preset/custom/auto profile (that mode simply isn't Adaptive → we return).

        - reapply=False (mode selected / game entry): mark applied so the per-tick
          watcher can stop recomputing every 5 s. `_reapply_fans` does the actual
          hardware write on these paths.
        - reapply=True  (periodic ~30 min re-fit): recompute and re-drive the hardware
          only when the fit shifted appreciably (anti-churn vs the last driven curve).

        Cheap O(1) guards (running game + adaptive mode) run FIRST so the histogram is
        never walked otherwise. Never raises; never fakes an apply."""
        try:
            appid = self._current_appid
            if appid is None or not self._fan_curves.is_adaptive(appid):
                return
            points = self._adaptive_curve_points(appid)
            if points is None:
                return  # not enough real data yet → firmware auto stays (never-fake)
            if reapply and not fan_suggest.curve_changed(self._last_adaptive_points, points):
                return  # nothing worth re-driving → no thermal/eMMC churn
            self._last_adaptive_points = points
            self._reapply_fans()  # push the (re)computed curve to the hardware
            self._adaptive_applied = True  # per-session watcher can stop now
        except Exception:  # noqa: BLE001
            pass

    def _maybe_drive_adaptive_fan_curve(self) -> None:
        """On selecting Adaptive / entering a game (or mid-session once enough data
        lands), compute and drive the learned curve to the hardware."""
        self._drive_adaptive_fan_curve(reapply=False)

    def _maybe_reapply_adaptive_fan_curve(self) -> None:
        """A1: periodically (every ~30 min of play) re-fit and re-drive the adaptive
        curve so it follows the game's RECENT thermal pattern (the histogram decays)."""
        self._drive_adaptive_fan_curve(reapply=True)

    # ---- Telemetry ----------------------------------------------------------
    def _collect_sample(self):
        """Build one telemetry sample from live readers.

        Returns (appid, sample_dict) while in-game, or None when idle.
        Never raises; any error degrades to None (no sample recorded).
        """
        try:
            # Snapshot the appid once: this method now runs on a worker thread
            # (via asyncio.to_thread) and spans a ~120 ms gpu_busy burst + fan
            # I/O, during which an event-loop RPC could reassign _current_appid.
            # Reading it once keeps the guard, the setpoint, and the returned
            # appid consistent so a sample is never mislabelled across a game
            # switch (telemetry honesty).
            appid = self._current_appid
            if appid is None:
                return None

            pr = self._power_reader.read()
            fan = self._read_fans()  # includes EC RPM on devices without a hwmon fan

            # CPU / GPU temps — prefer labels "CPU" / "GPU", fall back to position
            temp_cpu, temp_gpu = extract_cpu_gpu_temps(fan)

            # Max RPM across all fans (None if no fans)
            fans = fan.get("fans") or []
            fan_rpms = [f["rpm"] for f in fans if f.get("rpm") is not None]
            fan_rpm = max(fan_rpms) if fan_rpms else None

            # Clamped effective setpoint (mirrors get_power_draw)
            pl1 = self._effective_levels(appid)[0]["pl1"]

            # boost = was the chip boosting at this PL1 (draw > PL1 + deadband)?
            # 1.0/0.0/None; its per-bin average = the honest "power-limited here?"
            # signal the learned band reads (tdp/suggest._satisfied).
            watts = pr.get("watts")
            boosting = auto_tdp.is_boosting(watts, pl1)
            boost = None if boosting is None else (1.0 if boosting else 0.0)

            sample = {
                "pl1": pl1,
                "watts": watts,
                "gpu_busy": pr.get("gpu_busy"),
                "boost": boost,
                "temp_cpu": temp_cpu,
                "temp_gpu": temp_gpu,
                "fan_rpm": fan_rpm,
            }
            return (appid, sample)
        except Exception:  # noqa: BLE001
            return None

    def _on_sample_collected(self, result) -> None:
        """Sampler callback after each stored sample (A1 re-apply cadence).

        *result* is the (appid, sample) tuple that was stored, or None when idle.
        Idle ticks don't count — the counter reflects real play time. Every
        _REAPPLY_EVERY_TICKS in-game samples (~30 min) trigger a learned re-fit.

        While the effective mode is Adaptive and we have NOT yet driven the learned
        curve this session, try the gated drive on every in-game tick — so the moment
        `enough_data` flips true mid-session the curve lands immediately instead of
        waiting up to ~30 min for the next re-fit tick. The cheap O(1) mode guard runs
        first (in `_drive_adaptive_fan_curve`), and once driven the flag stops the
        suggestion from being recomputed every 5 s (only the 30-min re-fit runs).
        """
        if result is None:
            return
        if not self._adaptive_applied:
            self._maybe_drive_adaptive_fan_curve()  # gated; sets _adaptive_applied on success
        self._reapply_ticks += 1
        if self._reapply_ticks >= self._REAPPLY_EVERY_TICKS:
            self._reapply_ticks = 0
            self._maybe_reapply_adaptive_fan_curve()

    async def get_telemetry(self, appid=None) -> dict:
        self._init()
        key = str(appid) if appid is not None else self._current_appid
        if key is None:
            return {"samples_n": 0, "by_pl1": {}, "recent": []}
        return self._telemetry.aggregate(key)

    async def reset_telemetry(self) -> bool:
        """Wipe ALL learned usage data (TDP + fan) — start from scratch. Does NOT
        touch the user's manual TDP/fan profiles. The live windows are cleared too so
        the loop doesn't carry stale signal into the freshly-empty model."""
        self._init()
        self._telemetry.clear()
        self._reset_auto_windows()
        return True

    def _start_sampler(self) -> None:
        """Start the telemetry sampler and reset the ~30 min re-apply cadence so it
        aligns to when learning actually (re)begins — otherwise toggling telemetry
        mid-game would let `_reapply_ticks` drift out of phase with real dwell."""
        self._reapply_ticks = 0
        self._sampler.start()

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
            self._start_sampler()
        else:
            self._sampler.stop()  # also flushes any buffered samples
        return enabled

    async def get_learning_status(self) -> dict:
        """Capability + opt-in snapshot for the persistent learning banner (shown
        under the DeviceHeader). Reports what THIS device can actually learn:
        `tdp_supported` = a real TDP write backend exists; `fan_supported` = the
        device can WRITE fan curves (Null backends read-only → False). The banner
        combines these with the live running game (read on the frontend) to say —
        honestly — what is being learned, or that learning is paused when
        telemetry is off. Never claims to learn something this device can't."""
        self._init()
        return {
            "telemetry_enabled": bool(self._settings.get("telemetry_enabled", True)),
            "tdp_supported": bool(self._tdp_backend.supported),
            "fan_supported": bool(self._fan_ctrl.supported),
        }

    async def get_unlock_battery_max(self) -> bool:
        self._init()
        return bool(self._settings.get("unlock_battery_max", False))

    async def set_unlock_battery_max(self, enabled: bool) -> bool:
        """Opt in/out of using the firmware max on battery. Re-applies TDP so the
        new ceiling (and any re-clamp of the current setpoint) takes effect now."""
        self._init()
        enabled = bool(enabled)
        self._settings["unlock_battery_max"] = enabled
        self._save()
        self._reapply_tdp()
        return enabled

    def _qam_boost_active(self) -> bool:
        """The QAM-open responsive floor applies ONLY when its opt-in setting is on
        AND the UI is open. Default OFF → the auto loop shows the REAL in-game TDP
        with the QAM open (never inflates the number behind the menu). When ON, the
        user accepts the menu-time bump for fluidity."""
        return self._ui_active and bool(self._settings.get("qam_tdp_boost", False))

    async def get_qam_tdp_boost(self) -> bool:
        self._init()
        return bool(self._settings.get("qam_tdp_boost", False))

    async def set_qam_tdp_boost(self, enabled: bool) -> bool:
        """Opt in/out of raising PL1 while the QAM is open. When turning OFF while the
        UI is open we do NOT force PL1 back down — the auto loop will settle it to the
        real in-game value on its next tick (never fake, no jarring drop)."""
        self._init()
        enabled = bool(enabled)
        self._settings["qam_tdp_boost"] = enabled
        self._save()
        return enabled

    # ---- Auto-TDP loop ------------------------------------------------------
    def _start_auto_loop(self) -> None:
        if self._auto_task is not None and not self._auto_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop in tests — skip task creation safely
        self._reset_auto_windows()  # start each auto session with fresh windows
        self._auto_task = asyncio.create_task(self._auto_loop())

    def _stop_auto_loop(self) -> None:
        if self._auto_task is not None:
            self._auto_task.cancel()
            self._auto_task = None

    def _clear_auto_windows(self) -> None:
        """Empty the GPU% window — keeping it HOMOGENEOUS at the current PL1. Called
        after every applied PL1 change so decide never averages GPU% across
        different setpoints (samples taken at the OLD PL1 no longer describe the new
        one)."""
        self._gpu_window = []

    def _reset_auto_windows(self) -> None:
        """Full reset: clear the windows AND the slack counter, so a game change /
        loop (re)start / telemetry wipe never carries stale signal into the fresh
        state. (A mere PL1 change clears only the windows — decide already zeroes
        slack itself on any UP/DOWN, so don't double-reset it there.)"""
        self._clear_auto_windows()
        self._slack_ticks = 0

    async def _auto_loop(self) -> None:
        """Autonomous, band-DECOUPLED GPU-driven controller. Runs over the full
        device range [min_w, active_max]: every 2 s it feeds the rolling GPU%
        window to auto_tdp.decide, which converges on the knee and HOLDS (dead-band
        + temporal gate = no sawtooth), stepping up on GPU saturation and down after
        sustained GPU headroom. Watts/boost are NOT used for the decision — on a
        power-limited game the draw follows PL1, so any draw signal is confounded
        (measured on-device: 35 W cap / 80% GPU held at max forever). The learned
        band never caps it. Degrades to HOLD on devices without gpu_busy (Claw)."""
        while True:
            try:
                await asyncio.sleep(2)
                # Auto-TDP is a per-GAME dynamic control: don't adjust the global
                # setpoint from desktop/loading activity. Idle → drop stale window
                # so re-entry into a game starts homogeneous.
                if self._current_appid is None:
                    self._reset_auto_windows()
                    continue
                # Download mode owns the setpoint (min) — the loop must not fight it.
                # Drop the window so post-eco decisions start from fresh samples taken
                # at the real PL1, not stale ones from before eco pinned it to min.
                if self._settings.get("eco_enabled"):
                    self._reset_auto_windows()
                    continue
                # read() sub-samples gpu_busy over a short blocking burst -> off
                # the event loop so it can't stall other Decky RPC handling.
                pr = await asyncio.to_thread(self._power_reader.read)
                levels, active, _ac = self._effective_levels(self._current_appid)
                cur = levels["pl1"]
                lim = self._limits()

                self._gpu_window.append(pr.get("gpu_busy"))
                del self._gpu_window[:-_AUTO_WINDOW]

                floor = auto_tdp.effective_floor(lim.min_w, self._qam_boost_active())
                nxt, self._slack_ticks = auto_tdp.decide(
                    cur, self._gpu_window, self._slack_ticks, floor, active)
                if nxt != cur:
                    self._tdp_profiles.set_pl1(self._auto_scope(), nxt, appid=self._current_appid)
                    self._reapply_tdp()
                    # PL1 changed → drop the now-stale window (samples taken at the
                    # OLD setpoint) so the next reads are homogeneous at the new PL1.
                    self._clear_auto_windows()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                pass  # loop must never die

    # ---- Power draw + auto-TDP RPCs -----------------------------------------
    def _ui_floor_engaged(self) -> bool:
        """True ONLY when the QAM-open responsive floor is REALLY holding PL1 above
        where the auto loop would otherwise park it — so the UI can honestly say
        "this number is raised for the menu, not the in-game value". False when the
        game already demands >= the responsive floor (the number IS the in-game one),
        or when not auto / no game / UI closed. Never-fake: don't claim a raise that
        isn't happening."""
        if not (self._qam_boost_active() and self._current_appid is not None
                and bool(self._settings.get("auto_tdp"))):
            return False
        lim = self._limits()
        floor = auto_tdp.effective_floor(lim.min_w, True)
        if floor <= lim.min_w:
            return False  # device min already >= responsive floor → no raise
        # The floor bites only when the loop's PL1 sits AT the responsive floor
        # (it wanted lower / is being held up). A demanding game parks above it.
        pl1 = self._effective_levels(self._current_appid)[0]["pl1"]
        return pl1 <= floor

    async def get_power_draw(self) -> dict:
        self._init()
        pr = await asyncio.to_thread(self._power_reader.read)
        auto = bool(self._settings.get("auto_tdp"))
        setpoint = self._effective_levels(self._current_appid)[0]["pl1"]
        return {
            "watts": pr["watts"],
            "gpu_busy": pr["gpu_busy"],
            "auto_tdp": auto,
            "setpoint": setpoint,
            "ui_floor_engaged": self._ui_floor_engaged(),
        }

    async def set_auto_tdp(self, enabled: bool) -> dict:
        self._init()
        self._clear_eco()
        self._settings["auto_tdp"] = bool(enabled)
        self._save()
        if enabled:
            self._start_auto_loop()
        else:
            self._stop_auto_loop()
        return {"auto_tdp": bool(enabled)}

    async def set_ui_active(self, enabled: bool) -> bool:
        """The plugin UI (QAM panel) opened/closed. When the opt-in ``qam_tdp_boost``
        setting is on, while open the AUTO loop uses a higher responsive floor
        (CPU-bound menu render stays fluid) and we bump PL1 to that floor IMMEDIATELY
        (only if it's currently LOWER) so the menu is snappy without waiting for the
        loop to ramp — a real, honest PL1 change surfaced via ui_floor_engaged. With
        the setting OFF (default) opening the QAM changes NOTHING: the auto loop shows
        the REAL in-game TDP. Only affects AUTO mode + a running game."""
        self._init()
        self._ui_active = bool(enabled)
        if (self._qam_boost_active() and self._current_appid is not None
                and bool(self._settings.get("auto_tdp"))):
            lim = self._limits()
            floor = auto_tdp.effective_floor(lim.min_w, True)
            cur = self._effective_levels(self._current_appid)[0]["pl1"]
            if cur < floor:  # only raise if actually below the responsive floor
                self._tdp_profiles.set_pl1(self._auto_scope(), floor,
                                           appid=self._current_appid)
                self._reapply_tdp()
                self._clear_auto_windows()  # PL1 changed → window is now stale
        return self._ui_active

    # ---- TDP helpers + RPCs -------------------------------------------------
    def _limits(self):
        """Device TDP limits with the user's battery-unlock preference applied (a
        single chokepoint so every clamp/limit path honours the Ajustes toggle)."""
        return self._tdp_backend.get_limits().unlocked(
            bool(self._settings.get("unlock_battery_max", False)))

    def _effective_levels(self, appid=None, on_ac=None):
        """Clamped {pl1,pl2,pl3} for a scope at the active (on_ac) ceiling, plus the
        ceiling. Single source for every loop/RPC that needs the applied setpoint."""
        limits = self._limits()
        ac = read_on_ac() if on_ac is None else on_ac
        active = self._active_max(limits, ac)
        ll = self._cap_level_limits(self._tdp_backend.level_limits(), active)
        levels = self._clamp_levels(self._tdp_profiles.effective(appid), limits, active, ll)
        if self._settings.get("eco_enabled"):
            # Download mode: force every rail to the device minimum, overriding any
            # profile/scope (this is the single chokepoint every RPC + reapply reads).
            # Clamp through the rail floors so the reported levels equal what the
            # firmware actually accepts (a rail's own min may be > min_w).
            m = limits.min_w
            levels = self._clamp_levels({"pl1": m, "pl2": m, "pl3": m}, limits, active, ll)
        return levels, active, ac

    def _cap_level_limits(self, ll: dict, active_max: int) -> dict:
        """Cap PL1 (sustained) to the active power ceiling. The boost rails PL2/PL3
        keep their FIRMWARE max — they are short-term limits that legitimately exceed
        PL1 (SPPT 45 / FPPT 55 on the Ally). Capping them to PL1's ceiling left the
        additive boost offsets at 0 once PL1 reached the max (e.g. unlocked to 35 W)."""
        out = {}
        for key, b in ll.items():
            if key == "pl1":
                hi = min(b["max"], active_max)
                out[key] = {"min": min(b["min"], hi), "max": hi}
            else:
                out[key] = {"min": b["min"], "max": b["max"]}
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

    # ---- Learned TDP band (G2) ----------------------------------------------
    def _tdp_learned_info(self, appid=None) -> dict:
        """Display-facing learned-band info for a game (honest reasons).

        reason ∈ {disabled, no_game, no_data, too_few, one_level, ok}. The band
        fields are None unless ``enough``. ``minutes`` = total in-game dwell learned.
        """
        def unavail(reason):
            return {"floor": None, "ceil": None, "seed": None,
                    "observed_lo": None, "observed_hi": None,
                    "enough": False, "reason": reason, "minutes": 0,
                    "target_minutes": tdp_suggest.MIN_MINUTES}

        if not bool(self._settings.get("telemetry_enabled", True)):
            return unavail("disabled")
        key = str(appid) if appid is not None else self._current_appid
        if key is None:
            return unavail("no_game")
        try:
            by_pl1 = self._telemetry.aggregate(key)["by_pl1"]
            band = tdp_suggest.learned_band(by_pl1)
            minutes = round(sum(r["seconds"] for r in by_pl1.values()) / 60) if by_pl1 else 0
            return {**band, "minutes": minutes, "target_minutes": tdp_suggest.MIN_MINUTES}
        except Exception:  # noqa: BLE001
            return unavail("error")

    def _auto_scope(self) -> str:
        """The TDP/fan profile scope the auto machinery writes to (game when one is
        running, else global)."""
        return "game" if self._current_appid else "global"

    def _reapply_tdp(self, on_ac=None):
        self._init()
        lv, _active, ac = self._effective_levels(self._current_appid, on_ac)
        return self._tdp_backend.set_levels(lv["pl1"], lv["pl2"], lv["pl3"], ac)

    def _reapply_all(self, on_ac=None) -> None:
        """Lifecycle callback: re-assert TDP, the fan curve, the charge limit and the
        CPU controls (resume/AC — firmware may drop these across a suspend)."""
        self._reapply_tdp(on_ac)
        self._reapply_fans()
        self._apply_charge_limit()
        self._apply_cpu()

    # ---- Battery + charge limit --------------------------------------------
    def _apply_charge_limit(self) -> None:
        """Write the persisted charge limit (or 100 = no cap when disabled). Safe to
        call on any device — a Null backend no-ops."""
        if not self._charge_limit.supported:
            return
        enabled = bool(self._settings.get("charge_limit_enabled", False))
        if enabled:
            self._charge_limit.set(int(self._settings.get("charge_limit_percent", 80)))
        else:
            # backend-specific "no cap" (ASUS 100, Deck 0)
            self._charge_limit.disable()

    def _charge_limit_state(self) -> dict:
        lo, hi = self._charge_limit.range()
        enabled = bool(self._settings.get("charge_limit_enabled", False))
        percent = int(self._settings.get("charge_limit_percent", 80))
        fixed = getattr(self._charge_limit, "fixed_percent", None)
        if not self._charge_limit.adjustable and fixed is not None:
            # Fixed-cap backend (Lenovo conservation): report the firmware level so
            # the UI can state it explicitly (e.g. "caps at 80%").
            percent = fixed
        elif enabled and self._charge_limit.supported and self._charge_limit.adjustable:
            # never-fake: report what the firmware actually holds (it may clamp our write).
            actual = self._charge_limit.get()
            if actual is not None:
                percent = actual
        return {
            "supported": self._charge_limit.supported,
            "adjustable": self._charge_limit.adjustable,
            "enabled": enabled,
            "percent": percent,
            "min": lo,
            "max": hi,
        }

    async def get_battery_state(self) -> dict:
        self._init()
        battery = self._battery.read()
        # Single AC-online source (same one every TDP clamp uses).
        battery["ac_online"] = read_on_ac()
        return {"battery": battery, "charge_limit": self._charge_limit_state()}

    # ---- CPU (SMT + boost) --------------------------------------------------
    def _apply_cpu(self) -> None:
        """Re-assert the persisted SMT + boost state (safe no-op where unsupported).
        In download mode, boost is forced off regardless of the saved setting."""
        if self._smt.supported:
            self._smt.set(bool(self._settings.get("smt_enabled", True)))
        if self._boost.supported:
            eco = self._settings.get("eco_enabled", False)
            self._boost.set(False if eco else bool(self._settings.get("boost_enabled", True)))

    def _clear_eco(self) -> None:
        """Manual control taken → exit download mode and restore the normal TDP/boost
        state. Brightness is NOT touched here (FE-only; the persistent controller
        stops driving it and the user keeps whatever they set). B1 in the design."""
        if self._settings.get("eco_enabled"):
            self._settings["eco_enabled"] = False
            self._save()
            self._reapply_all()

    def _eco_state(self) -> dict:
        return {
            "enabled": bool(self._settings.get("eco_enabled", False)),
            "tdp_min_w": self._limits().min_w,
            "affects_boost": self._boost.supported,
            # The brightness % to wake back to (pre-eco snapshot).
            "wake_brightness": int(self._settings.get("eco_brightness", 40)),
        }

    async def get_eco_state(self) -> dict:
        self._init()
        return self._eco_state()

    async def set_eco(self, enabled: bool, current_brightness: int) -> dict:
        """Toggle download mode. On enable, snapshot the current brightness (to wake
        back to) and apply the override (TDP min + boost off) via _reapply_all; on
        disable, drop the override and re-apply the normal profile/boost."""
        self._init()
        # Snapshot the wake brightness only if it's a real reading (> 0). The FE may
        # pass 0 while brightness is still loading; storing 0 would restore the screen
        # to black on exit (unrecoverable from the card). Keep the previous value then.
        if enabled and int(current_brightness) > 0:
            self._settings["eco_brightness"] = int(current_brightness)
        self._settings["eco_enabled"] = bool(enabled)
        self._save()
        self._reapply_all()
        return self._eco_state()

    def _cpu_state(self) -> dict:
        info = self._cpu_info
        return {
            # Real silicon name (same source as get_device) so the CpuCard and the
            # DeviceHeader never show two different CPU names on the same screen.
            "chip": self._chip or self._device.chip,
            "cores": info["cores"],
            "threads": info["threads"],
            "base_khz": info["base_khz"],
            "max_khz": info["max_khz"],
            "smt": {"supported": self._smt.supported, "enabled": self._smt.enabled()},
            "boost": {"supported": self._boost.supported, "enabled": self._boost.enabled()},
        }

    async def get_cpu_state(self) -> dict:
        self._init()
        return self._cpu_state()

    async def set_smt(self, enabled: bool) -> dict:
        self._init()
        self._clear_eco()
        self._settings["smt_enabled"] = bool(enabled)
        self._save()
        if self._smt.supported:
            self._smt.set(bool(enabled))
        return self._cpu_state()

    async def set_cpu_boost(self, enabled: bool) -> dict:
        self._init()
        self._clear_eco()
        self._settings["boost_enabled"] = bool(enabled)
        self._save()
        if self._boost.supported:
            self._boost.set(bool(enabled))
        return self._cpu_state()

    async def set_charge_limit(self, enabled: bool, percent: int) -> dict:
        """Enable/disable the charge cap and set its threshold. Persists, applies via
        readback, and returns the resulting charge_limit block."""
        self._init()
        self._settings["charge_limit_enabled"] = bool(enabled)
        self._settings["charge_limit_percent"] = int(percent)
        self._save()
        self._apply_charge_limit()
        return self._charge_limit_state()

    async def get_tdp_state(self) -> dict:
        self._init()
        return self._tdp_state()

    def _tdp_state(self) -> dict:
        levels, active, ac = self._effective_levels(self._current_appid)
        global_levels, _active, _ac = self._effective_levels(None, ac)
        limits = self._limits()
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
            # The learned band for this game (powers the separate TDP suggestion card).
            # The battery↔performance dial that picks a value inside it is now LOCAL UI
            # state — applying it is a fixed manual setpoint, not a loop parameter.
            "learned": self._tdp_learned_info(self._current_appid),
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
        self._clear_eco()  # manual TDP change exits download mode (after scope is valid)
        limits = self._limits()
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
        self._clear_eco()
        self._tdp_profiles.set_offsets(resolved, off2, off3, appid=appid)
        res = self._reapply_tdp()
        # requested_w/applied_w reflect resulting sustained pl1 (readback), not the offsets
        return {"requested_w": res.requested_w, "applied_w": res.applied_w,
                "ok": res.ok, "detail": res.detail}

    async def reset_tdp_auto(self, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is not None:  # invalid scope → no-op (never from the UI)
            self._clear_eco()
            self._tdp_profiles.set_auto(resolved, appid=appid)
            self._reapply_tdp()
        # Always return the full new state so the UI updates badge + sliders in ONE
        # round-trip (no separate get_tdp_state) — immediate, and a consistent
        # TdpState shape (the frontend does setTdp with it).
        return self._tdp_state()

    async def create_game_profile(self, appid) -> None:
        self._init()
        self._tdp_profiles.create_game_from_global(appid)
        self._current_appid = str(appid)

    async def set_current_game(self, appid) -> dict:
        self._init()
        self._current_appid = str(appid) if appid is not None else None
        self._reset_auto_windows()  # don't let the previous game's signal gate the new one
        self._reapply_ticks = 0        # A1: fresh ~30 min re-fit window for the new game
        self._adaptive_applied = False  # re-arm the mid-session adaptive drive for this game
        self._last_adaptive_points = None  # anti-churn baseline resets with the game
        # Auto-TDP no longer seeds PL1 from the learned band: the loop is band-decoupled
        # and explores to its own level. The learned band is a separate, explicit
        # suggestion (apply a fixed value) — see the UI. `_reapply_all` drives the
        # effective fan curve, including the adaptive learned curve when that mode is on.
        self._maybe_drive_adaptive_fan_curve()  # track + drive if adaptive with enough data
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
                self._start_sampler()
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
