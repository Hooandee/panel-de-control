import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime

import decky

# py_modules/ is on sys.path → import TOP-LEVEL (never `from py_modules.x import`).
import auto_tdp
import device_registry
import osinfo
import self_updater
from version import read_version
from settings_store import SettingsStore
from tdp import factory as tdp_factory
from tdp import suggest as tdp_suggest
from tdp.types import TdpResult
from tdp_profiles import ProfileStore
from power_presets import PowerPresetStore
from lifecycle import LifecycleManager, read_on_ac
from fans.hwmon import FanReader, extract_cpu_gpu_temps
from fans import control as fan_control
from fans import legion_ec
from fans import expose as fan_expose
from fans import presets as fan_presets
from fans import suggest as fan_suggest
from fan_curves import FanCurveStore
from launch import tools as launch_tools
from launch import proton_caps
from launch import custom_vars as launch_custom_vars
from display.color_store import ColorStore, sanitize_calibration
from display.gamescope import GamescopeColorBackend, run_gamescopectl
from display.oled_look import oled_look_for
from display.const import NATIVE as COLOR_NATIVE, FIELDS as COLOR_FIELDS, CALIBRATION as COLOR_CALIBRATION
from display.night_store import NightStore
from display.night import is_night_active
from display import presets as color_presets
from display.hdr import HdrBackend
from gpu.clock import select_gpu_clock
from power.reader import PowerReader
from battery.reader import BatteryReader
from battery.charge_limit import select_charge_limit
from audio.eq_store import EqStore
from audio.pipewire import PipeWireEq
from audio.profile_store import AudioProfileStore
from audio import presets as audio_presets
from audio import safe as audio_safe
from audio import tone as audio_tone
from cpu.info import read_cpu_info, read_cpu_model
from cpu.controls import CoreControl, SmtControl, select_boost
from cpu.profiles import CpuProfileStore
from telemetry.store import TelemetryStore
from telemetry.sampler import TelemetrySampler
from controllers import detect as controller_detect
from controllers import hhd as controller_hhd
from controllers import conflict as controller_conflict
from controllers import factory as controller_factory
from controllers.store import RemapStore
from controllers.dbus import IpDbus
from sysfs import read_str
from report import collector as report_collector
from report import client as report_client

# Bug reporter: the app slug (routes to the right GitHub repo, server-side) and the
# collector endpoint. The URL is set to the deployed Vercel service; overridable via
# env for testing. The plugin only POSTs here; it can never read a report back.
_REPORT_APP = "panel-de-control"
_REPORT_SERVICE_URL = os.environ.get(
    "PDC_REPORT_URL", "https://bug-collector-khaki.vercel.app/api/report"
)

# Auto-TDP rolling window: last N samples (~2 s apart) the control law reads. It
# measures the FREQUENCY of boost over the window (not an instant), so it is longer
# than the old reactive window; the up-trigger still uses the recent peak to reject
# transient dips. See py_modules/auto_tdp.py.
_AUTO_WINDOW = 10
# How often the audio EQ watcher checks the active output route (headphones vs speakers)
# to re-apply the per-route curve with the QAM closed.
_AUDIO_POLL_S = 4
# Watts of divergence before we treat a firmware PL1 read as an external change to
# adopt (above rounding/settling jitter).
_EXTERNAL_TDP_THRESHOLD = 2

_NIGHT_TICK_S = 30  # how often the night-mode clock checks for a schedule-edge crossing

# "custom" = our TDP owns the rails, vs a named platform_profile mode.
_CUSTOM_MODE = "custom"


def _now_minutes() -> int:
    t = datetime.now()
    return t.hour * 60 + t.minute

DEFAULTS = {
    # Persisted settings keys go here; SettingsStore merges these over stored values.
    # (Per-game TDP profiles live in their own store, tdp_profiles.py.)
    # One-time-migration flags: SettingsStore drops keys not in DEFAULTS, so these MUST
    # be declared here or the migration re-runs every load and clobbers the new stores.
    "_potencia_scope_migrated": False,
    "_cpu_scope_migrated": False,
    "_hdr_scope_migrated": False,
    "auto_tdp": False,
    # Learn from usage (local-only telemetry powering fan-curve suggestions). Opt-out:
    # when False the sampler never runs — nothing is read or written during play.
    "telemetry_enabled": True,
    # Opt-in: raise the on-battery TDP ceiling to the firmware/charger max. Default
    # off (we cap battery below the firmware max for battery life); the user accepts
    # the drain when enabling. The firmware itself allows the same max either way.
    "unlock_battery_max": False,
    "cooler_boost": False,
    # Opt-in: while the QAM/plugin UI is open, raise PL1 to a responsive floor so the
    # CPU-bound menu render stays fluid. Default OFF for honesty — raising TDP behind
    # the menu would show an inflated number vs the REAL in-game TDP the user wants to
    # see with the QAM open. When ON, the user accepts the menu-time bump for fluidity.
    "qam_tdp_boost": False,
    # Master switch: when False we stop writing the TDP rails and Potencia drops to
    # monitor-only, handing TDP to another tool.
    "tdp_control_enabled": True,
    # Modules the user turned off in the customization editor (generic ids only;
    # power/learning are folded from tdp_control_enabled/telemetry_enabled).
    "disabled_modules": [],
    # One-time notices (SettingsStore drops keys not in DEFAULTS).
    "seen_tdp_conflict_takeover": False,
    "seen_autotdp_notice": False,
    # HHD's tdp_enable saved when we take control, to restore later. None = never took it.
    "hhd_tdp_prev": None,
    # HDR output on/off (only meaningful on HDR-capable panels — see device.hdr).
    "hdr_enabled": False,
    # Battery charge limit: when enabled, cap charging at `charge_limit_percent`
    # (protects battery longevity). Disabled → firmware default (100%).
    "charge_limit_enabled": False,
    "charge_limit_percent": 80,
    # CPU controls default to full performance (SMT + boost on) — the stock state.
    "smt_enabled": True,
    "boost_enabled": True,
    # Active physical cores. None = all cores (stock); an int caps the count.
    "active_cores": None,
    # GPU clock window (MHz). manual=False → leave the GPU on auto (we don't touch
    # it); True → pin/limit to [min,max]. min/max None until the user sets them.
    "gpu_clock_manual": False,
    "gpu_clock_min": None,
    "gpu_clock_max": None,
    # Download mode (low power while a game downloads unattended): TDP→min, boost
    # off, ambient screen dim. `eco_brightness` = the pre-eco brightness % to wake
    # back to. Both restored/derived on exit; eco_enabled is a pure override.
    "eco_enabled": False,
    "eco_brightness": 40,
    # Opt-in experimental fan control on devices whose only channel is an unofficial
    # EC interface (Legion Go S). Default off → read-only monitor; on → EC curve
    # control with the RPM cap + temp guardian harness. The user accepts the risk.
    "fan_experimental": False,
    # Firmware performance mode (Legion Go original). "custom" = our TDP; a named mode
    # hands power+fan+LED to the firmware. Device-global; ignored where unsupported.
    "firmware_mode": "custom",
    # Audio EQ (Sonido): opt-in. Off = we never create the PipeWire EQ sink, audio is
    # untouched. On → the effective per-route/per-game curve is applied. The curves
    # themselves live in their own store (audio.json).
    "audio_eq_enabled": False,
    # Frontend UI preferences, mirrored here so they survive a reboot (the
    # frontend's localStorage cache does not). Opaque string map.
    "ui_prefs": {},
    # Launch-options pill usage counts ({pill_id: times applied}) → the editor
    # surfaces the ones you use most. Durable so it survives a reboot.
    "launch_usage": {},
    # User-defined launch variables (env NAME=VALUE / game args), reusable across
    # games. The library is global; the on/off is per-game (in Steam's string).
    "custom_launch_vars": [],
}


class Plugin:
    # Re-fit + re-apply the learned fan curve every this-many collected in-game
    # samples. The sampler ticks every 5 s only while in-game, so 360 × 5 s ≈ 30 min
    # of ACTUAL play — matching the telemetry histogram's ~30 min decay half-life so
    # the curve tracks the current thermal "zone" without explicit zone detection.
    _REAPPLY_EVERY_TICKS = 360

    # Calibration preview auto-reverts to the saved value after this many seconds
    # unless the user confirms — the "changing screen resolution" safety pattern.
    _COLOR_REVERT_SECS = 15

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
        self._power_presets = PowerPresetStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "power_presets.json"))
        # One-time migration: auto-TDP and GPU clock used to be flat global settings.
        # Seed them into the global Potencia profile so they take part in per-game scope.
        if not self._settings.get("_potencia_scope_migrated"):
            if self._settings.get("auto_tdp"):
                self._tdp_profiles.set_auto_tdp("global", True)
            if self._settings.get("gpu_clock_manual"):
                self._tdp_profiles.set_gpu_clock(
                    "global", True,
                    self._settings.get("gpu_clock_min") or 0,
                    self._settings.get("gpu_clock_max") or 0)
            self._settings["_potencia_scope_migrated"] = True
            self._store.save(self._settings)
        self._tdp_backend = tdp_factory.select_backend(self._device)
        # Safety self-heal: correct any stored TDP value an older version persisted
        # outside the device's real range (a bogus firmware max could leak in) so it can
        # never be applied — not merely clamped on read.
        _lim = self._limits()
        if self._tdp_profiles.sanitize(_lim.min_w, _lim.max_ac_w):
            decky.logger.info("Corrected out-of-range stored TDP profiles")
        # Which daemon owns the controller (HHD / InputPlumber / none). Detected
        # once — the resident daemon doesn't change at runtime. Probe never raises.
        self._controller = controller_detect.detect()
        # Cooperative controller remap: per-scope overrides store (global + per-game,
        # InputPlumber only — we own its remap) + the busctl dbus driver, both owned by
        # the InputPlumber backend. The factory picks ONE backend (HHD REST / IP dbus /
        # none). `_last_controller_overrides` gates the game-change re-apply so we only
        # touch the daemon when the effective profile actually changes.
        self._controller_backend = controller_factory.select_controller_backend(
            self._controller,
            RemapStore(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "controller_remap.json")),
            IpDbus(),
            self._device,
        )
        self._last_controller_overrides = None
        self._fan_reader = FanReader()
        # temp_fn feeds the software-loop backends (Steam Deck / Legion Go 2) the
        # live driving temp; hardware-curve backends (ASUS/MSI) ignore it.
        self._fan_ctrl = fan_control.select_fan_backend(
            self._device, temp_fn=self._driving_temp,
            experimental=bool(self._settings.get("fan_experimental", False)))
        # True only on a device with an opt-in experimental EC fan channel (Legion
        # Go S). DMI-only check (no EC I/O) → the UI shows the experimental toggle.
        try:
            from fans.legion_ec import LegionGoSFanBackend
            self._fan_experimental_available = LegionGoSFanBackend(root="/").supported
        except Exception:  # noqa: BLE001 — availability probe must never break load
            self._fan_experimental_available = False
        # MSI Claw only: the firmware fan curve is read-only-legible in the EC even
        # though the write backend is unsupported. Surface it as an informational
        # curve. Other devices get None (no EC dependency).
        self._ec_curve = fan_control.select_firmware_curve_reader(self._device)
        # Read-only EC RPM fallback for kernels whose driver publishes no hwmon fan node.
        self._ec_rpm = legion_ec.select_legion_rpm_reader(self._device)
        self._fan_curves = FanCurveStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "fan_curves.json")
        )
        # Pantalla: panel color. Saturation is per-game (store), calibration global.
        # Applied via gamescope atoms; the backend is probe-gated (UI hidden if the
        # host has no gamescope display) so nothing fake is ever shown.
        self._color = ColorStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "color.json")
        )
        # One-time migration: HDR on/off used to be a flat global setting; fold it into
        # the global color profile so it participates in per-game scope.
        if not self._settings.get("_hdr_scope_migrated"):
            if self._settings.get("hdr_enabled"):
                self._color.set_hdr("global", True)
            self._settings["_hdr_scope_migrated"] = True
            self._store.save(self._settings)
        # Intel/Xe needs gamescope composition forced for a color look to show in-game
        # (the LUT isn't carried by the HW color pipeline as it is on AMD).
        self._color_backend = GamescopeColorBackend(
            force_composite=(self._device.vendor == "intel")
        )
        decky.logger.info(
            "color: supported=%s (%s)",
            self._color_backend.supported, self._color_backend.probe_detail,
        )
        # Sonido: system audio EQ. Per-game + per output route (speaker/headphone),
        # applied via a PipeWire filter-chain sink. Opt-in — the sink is only created
        # when audio_eq_enabled. Backend is probe-gated (UI hidden without PipeWire).
        self._audio_eq = EqStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "audio.json")
        )
        self._audio = PipeWireEq(name=self._device.display_name)
        self._audio_profiles = AudioProfileStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "audio_profiles.json")
        )
        # Calibration safety: a change previews live but auto-reverts to the saved
        # value after _COLOR_REVERT_SECS unless confirmed (so a mis-drag to an
        # illegible screen self-heals even if the QAM closes). None = nothing pending.
        self._color_preview = None
        self._color_revert_task = None
        # Night mode: a scheduled warm shift on top of the calibration; _night_loop
        # re-applies on a schedule edge so it works with the QAM closed.
        self._night = NightStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "night.json")
        )
        self._night_task = None
        self._night_applied = False
        # Bounded startup task that re-asserts the display look once gamescope is ready.
        self._display_wait_task = None
        # HDR output on/off (gamescope). State lives in settings (hdr_enabled); gated to
        # HDR-capable panels with gamescope.
        self._hdr_backend = HdrBackend(run_gamescopectl)
        self._power_reader = PowerReader()
        self._battery = BatteryReader()
        self._charge_limit = select_charge_limit(self._device)
        self._smt = SmtControl()
        self._boost = select_boost()
        self._cores = CoreControl()
        self._cpu_profiles = CpuProfileStore(
            os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "cpu_profiles.json"))
        # One-time migration: SMT / boost / active cores used to be flat global settings.
        if not self._settings.get("_cpu_scope_migrated"):
            self._cpu_profiles.set_smt("global", bool(self._settings.get("smt_enabled", True)))
            self._cpu_profiles.set_boost("global", bool(self._settings.get("boost_enabled", True)))
            n = self._settings.get("active_cores")
            if n is not None:
                self._cpu_profiles.set_cores("global", int(n))
            self._settings["_cpu_scope_migrated"] = True
            self._store.save(self._settings)
        self._gpu_clock = select_gpu_clock(self._device)
        # Topology + freq range are static — read once (only SMT/boost state is live).
        # ORDER-CRITICAL: read AFTER CoreControl() above, which onlines all CPUs. The
        # kernel drops an offline CPU's topology/core_id, so counting cores here before
        # every core is online undercounts (e.g. 2 cores on an 8-core chip). Keep this
        # after self._cores.
        self._cpu_info = read_cpu_info()
        # Real silicon name (static) shown in the DeviceHeader instead of the hardcoded
        # table chip; read once here like _cpu_info. None on generic or when unreadable.
        self._chip = read_cpu_model() if not self._device.is_generic else None
        self._os_name = osinfo.read_os_name()
        self._current_appid = None
        # Last PL1 WE wrote to the firmware (readback). Adoption compares the live value
        # against this, not the profile, so it fires only for a real external change —
        # never on a stale/default read before our first apply or mid-transition (None).
        self._last_written_pl1 = None
        self._lifecycle = LifecycleManager(apply_cb=self._reapply_all)
        self._auto_task = None
        self._auto_setpoint = None
        # Audio EQ output-route watcher: last applied route + its loop task.
        self._audio_task = None
        self._audio_route_last = None
        self._audio_shutdown = False
        self._test_sample = None
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
        # count in-game samples toward the periodic adaptive re-fit.
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
        # Host tools the launch-option pills depend on (lsfg/mangohud/gamemode/…) +
        # distro. Static for the session; detected once. Never raises. Decky runs as
        # root, so detection must look under the real user's home, not root's.
        self._launch_tools = launch_tools.detect_tools(
            home=getattr(decky, "DECKY_USER_HOME", None) or os.path.expanduser("~")
        )
        self._ready = True

    def _save(self) -> None:
        self._store.save(self._settings)

    # ---- RPC methods (referenced by name from src/api.ts) -------------------
    async def get_version(self) -> str:
        self._init()
        return read_version()

    async def get_launch_tools(self) -> dict:
        self._init()
        return dict(self._launch_tools)

    async def get_proton_caps(self, compat_name: str = "") -> dict:
        """Which PROTON_* vars the given game's Proton build supports (read from its
        own script) → the editor only shows options that actually work there."""
        self._init()
        home = getattr(decky, "DECKY_USER_HOME", None) or os.path.expanduser("~")
        return proton_caps.detect_capabilities(compat_name, home=home)

    async def get_launch_usage(self) -> dict:
        self._init()
        usage = self._settings.get("launch_usage")
        return dict(usage) if isinstance(usage, dict) else {}

    async def bump_launch_usage(self, ids: list) -> bool:
        """Increment the apply-count for each given pill id (drives the Frecuentes row)."""
        self._init()
        usage = self._settings.get("launch_usage")
        usage = dict(usage) if isinstance(usage, dict) else {}
        for pid in ids or []:
            if isinstance(pid, str):
                usage[pid] = int(usage.get(pid, 0)) + 1
        self._settings["launch_usage"] = usage
        self._save()
        return True

    async def get_custom_launch_vars(self) -> list:
        """The reusable launch-variable library (shape-coerced)."""
        self._init()
        return launch_custom_vars.coerce_custom_vars(self._settings.get("custom_launch_vars"))

    async def set_custom_launch_vars(self, vars: list) -> list:
        """Persist the whole library; return the stored (coerced) list."""
        self._init()
        clean = launch_custom_vars.coerce_custom_vars(vars)
        self._settings["custom_launch_vars"] = clean
        self._save()
        return clean

    async def get_ui_prefs(self) -> dict:
        self._init()
        prefs = self._settings.get("ui_prefs")
        return dict(prefs) if isinstance(prefs, dict) else {}

    async def set_ui_prefs(self, updates: dict) -> bool:
        # A None value removes that key.
        self._init()
        prefs = self._settings.get("ui_prefs")
        # Copy: an unset key aliases the shared DEFAULTS dict; never mutate it.
        prefs = dict(prefs) if isinstance(prefs, dict) else {}
        if isinstance(updates, dict):
            for key, value in updates.items():
                if value is None:
                    prefs.pop(str(key), None)
                else:
                    prefs[str(key)] = str(value)
        self._settings["ui_prefs"] = prefs
        self._save()
        return True

    async def get_ui_modules(self) -> dict:
        """The user-disabled module set (generic ids + power/learning folded from
        their native settings). The frontend derives the effective state."""
        self._init()
        return {"disabled": self._user_disabled_all()}

    async def set_ui_module(self, module_id: str, disabled: bool) -> dict:
        """Enable/disable a module durably, then re-apply everything honestly so the
        newly-off machinery is released (fans→auto, TDP rails freed, loops idle)."""
        self._init()
        disabled = bool(disabled)
        if module_id in self._MODULE_SETTING:
            self._settings[self._MODULE_SETTING[module_id]] = not disabled
        elif module_id in self._GENERIC_MODULES:
            cur = set(self._disabled_modules())
            cur.add(module_id) if disabled else cur.discard(module_id)
            self._settings["disabled_modules"] = sorted(cur)
        else:
            return {"disabled": self._user_disabled_all()}  # unknown id → no-op
        self._save()
        self._reapply_all()   # already dispatches its subprocess work off-loop
        # Turning the power module off = stepping aside; hand HHD's TDP back, same
        # as set_tdp_control_enabled(False). Otherwise no manager drives the TDP.
        if module_id == "power" and disabled:
            await self._offload_call(self._restore_hhd_tdp)
        self._sync_sampler()  # learning may have (un)gained a consumer
        return {"disabled": self._user_disabled_all()}

    async def reset_modules(self) -> dict:
        """Reset the customization layout. Leaves the functional switches (TDP control,
        telemetry) as-is; a visual reset must not silently re-enable them."""
        self._init()
        self._settings["disabled_modules"] = []
        self._save()
        self._reapply_all()
        self._sync_sampler()
        return {"disabled": self._user_disabled_all()}

    async def check_update(self, force: bool = False) -> dict:
        self._init()
        return self_updater.check(force)

    async def install_update(self) -> dict:
        self._init()
        return self_updater.install()

    async def restart_loader(self) -> None:
        # Fire-and-forget: restarts Decky to load the just-installed files.
        self_updater.restart_loader()

    async def get_device(self) -> dict:
        self._init()
        d = asdict(self._device)
        # Show the REAL silicon name (cached in _init) rather than the hardcoded table
        # value, which can drift per unit/variant (e.g. Legion Go 2 = "Ryzen Z2
        # Extreme", not the Ally X's "Ryzen AI Z2 Extreme"). Falls back to the table
        # chip when the kernel exposes nothing.
        if self._chip:
            d["chip"] = self._chip
        # GPU generation for upscaler gating in Parámetros (FSR4 = rdna3/rdna4).
        d["gpu_gen"] = device_registry.gpu_generation(self._device.vendor, d["chip"])
        return d

    # ---- Bug reporter ------------------------------------------------------
    async def submit_report(self, categories=None, text: str = "", context=None) -> dict:
        """Collect a redacted diagnostic bundle and send it to the collector
        service. Write-only: the plugin can never read a report back. `context` is
        optional frontend-only diagnostics (e.g. a launch report's running-game
        snapshot). Falls back to saving the bundle on disk if the network send fails.
        Returns {ok, code, issue_url} or {ok:false, error, saved_path}."""
        self._init()
        home, hostname = self._redact_ids()
        try:
            bundle = await self._build_report_bundle(categories, text, home, hostname, context)
        except Exception as e:  # noqa: BLE001
            decky.logger.error("report bundle failed: %s", e)
            bundle = report_collector.build_bundle(
                app=_REPORT_APP, categories=categories, text=text,
                environment={}, capabilities={}, state={}, stores={}, logs=[],
                home=home, hostname=hostname,
            )
            bundle["error"] = "bundle_incomplete"
        # The POST is a blocking urllib call (up to 20s on a dead network); run it
        # off the event loop so the auto-TDP loop and other RPCs don't stall.
        res = await asyncio.get_running_loop().run_in_executor(
            None, lambda: report_client.submit(_REPORT_SERVICE_URL, bundle)
        )
        if res.get("ok"):
            decky.logger.info("report sent: %s", res.get("code"))
            return {"ok": True, "code": res["code"], "issue_url": res.get("issue_url")}
        path = report_client.save_local(
            getattr(decky, "DECKY_PLUGIN_LOG_DIR", "."), bundle
        )
        decky.logger.warning(
            "report send failed (%s); saved to %s", res.get("error"), path
        )
        return {"ok": False, "error": res.get("error", "unknown"), "saved_path": path}

    def _redact_ids(self):
        """(home, hostname) used to scrub PII from the bundle. Guarded."""
        home = getattr(decky, "DECKY_USER_HOME", None) or os.path.expanduser("~")
        try:
            import socket

            hostname = socket.gethostname()
        except Exception:  # noqa: BLE001
            hostname = None
        return home, hostname

    async def _build_report_bundle(self, categories, text, home, hostname, context=None) -> dict:
        """Gather every diagnostic piece (device, live state, stores, logs) and hand
        it to the collector for assembly + redaction. Each state fetch is guarded so
        a single failing subsystem never blocks the report."""
        loop = asyncio.get_running_loop()

        async def _safe(coro):
            try:
                return await coro
            except Exception:  # noqa: BLE001
                return {}

        states = {
            "device": await _safe(self.get_device()),
            "tdp": await _safe(self.get_tdp_state()),
            "fan_curve": await _safe(self.get_fan_curve_state()),
            "fan_monitor": await _safe(self.get_fan_state()),
            "battery": await _safe(self.get_battery_state()),
            "cpu": await _safe(self.get_cpu_state()),
            "color": await _safe(self.get_color_state()),
            "gpu": await _safe(self.get_gpu_clock()),
            # get_controller_config can block (HHD localhost HTTP / busctl spawn) →
            # run it off the event loop, unlike the cheap sysfs reads above.
            "controller": await loop.run_in_executor(None, self._safe_controller_config),
            "power": await _safe(self.get_power_draw()),
            "eco": await _safe(self.get_eco_state()),
            "audio": await _safe(self.get_audio_state()),
            "audio_diag": await _safe(self._offload_call(self._audio.diagnostics)),
            # Detected tools + current game + the frontend's running-game snapshot.
            "launch": self._launch_report_state(context),
        }
        logs = report_collector.tail_logs(
            getattr(decky, "DECKY_PLUGIN_LOG_DIR", ""), home=home, hostname=hostname
        )
        # Bounded filesystem listing of the raw sysfs support surfaces (fan/temp
        # chips, vendor WMI attributes, battery/charge nodes, ACPI-call + modules)
        # so an unrecognised device is diagnosable from what actually exists.
        snapshot = report_collector.sysfs_snapshot(home=home, hostname=hostname)
        # dmesg/journalctl are blocking subprocess calls (up to a few seconds each);
        # run them off the event loop so the auto-TDP loop and other RPCs don't stall.
        kernel = await loop.run_in_executor(
            None,
            lambda: report_collector.kernel_logs(
                self._run_capture,
                extra=report_collector.controller_daemon_cmds(
                    self._controller_backend.manager
                ),
                home=home,
                hostname=hostname,
            ),
        )
        return report_collector.build_bundle(
            app=_REPORT_APP,
            categories=categories,
            text=text,
            environment=self._report_environment(),
            capabilities=report_collector.capabilities_from(states),
            state=states,
            stores=self._report_stores(),
            logs=logs,
            kernel=kernel,
            sysfs=snapshot,
            home=home,
            hostname=hostname,
        )

    def _launch_report_state(self, context) -> dict:
        """Launch-options triage: tools, current game, custom-var count, and the
        frontend snapshot. Never raises."""
        try:
            tools = dict(self._launch_tools) if isinstance(self._launch_tools, dict) else {}
        except Exception:  # noqa: BLE001
            tools = {}
        try:
            n_custom = len(launch_custom_vars.coerce_custom_vars(self._settings.get("custom_launch_vars")))
        except Exception:  # noqa: BLE001
            n_custom = 0
        return {
            "tools": tools,
            "current_appid": self._current_appid,
            "custom_var_count": n_custom,
            "frontend": context if isinstance(context, dict) else {},
        }

    def _safe_controller_config(self) -> dict:
        try:
            return self._controller_backend.get_config()
        except Exception:  # noqa: BLE001
            return {}

    def _run_capture(self, cmd) -> str | None:
        """Run a diagnostic command and return its stdout (or None). Root + a clean
        env (the frozen runtime's LD_LIBRARY_PATH breaks system binaries). Guarded."""
        try:
            import subprocess

            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                env=controller_detect.clean_env(),
            )  # noqa: S603
            return r.stdout or ""
        except Exception:  # noqa: BLE001
            return None

    def _report_environment(self) -> dict:
        """Host identity + versions. Serials are deliberately NOT read (and any
        serial-like field is scrubbed downstream)."""
        os_name = self._os_name
        kernel = None
        try:
            u = os.uname()
            kernel = f"{u.sysname} {u.release}"
        except Exception:  # noqa: BLE001
            pass
        return {
            "plugin_version": read_version(),
            "decky_version": getattr(decky, "DECKY_VERSION", None),
            "device_key": getattr(self._device, "key", None),
            "product_name": read_str("/sys/class/dmi/id/product_name"),
            "product_family": read_str("/sys/class/dmi/id/product_family"),
            "board_name": read_str("/sys/class/dmi/id/board_name"),
            "os": os_name,
            "kernel": kernel,
        }

    def _report_stores(self) -> dict:
        """The persisted JSON stores (settings + per-game profiles/curves + learned
        telemetry). All bounded in size; telemetry self-caps at 50 games."""
        base = decky.DECKY_PLUGIN_SETTINGS_DIR

        def _rj(name):
            try:
                with open(os.path.join(base, name)) as f:
                    return json.load(f)
            except Exception:  # noqa: BLE001
                return None

        return {
            "settings": self._settings,
            "tdp_profiles": _rj("tdp_profiles.json"),
            "fan_curves": _rj("fan_curves.json"),
            "color": _rj("color.json"),
            "audio": _rj("audio.json"),
            "controller_remap": _rj("controller_remap.json"),
            "telemetry": _rj("telemetry.json"),
        }

    # ---- Mandos (controller manager + conflict) ----------------------------
    # One backend per device (factory), mirroring the TDP backend: each RPC is a
    # one-line delegation, no per-manager if/elif here. The config carries
    # manager / manager_version / supported so the UI needs a single round-trip.
    # get_config / set_button / reset spawn busctl (InputPlumber) or hit HHD's local
    # HTTP — blocking work that must stay off the event loop (a busctl stall while the
    # daemon re-grabs the pad would freeze the QAM). All offloaded via _offload_call.
    async def get_controller_config(self) -> dict:
        self._init()
        return await self._offload_call(
            lambda: self._controller_backend.get_config(self._current_appid))

    async def set_controller_button(self, source: str, targets: list,
                                    scope: str = "global", appid=None) -> dict:
        """Remap one extra button in a scope (global / a game; InputPlumber only,
        no-op on others). Editing tracks the applied set so the game-change re-apply
        can tell whether anything changed."""
        self._init()
        scope = self._resolve_scope(scope, appid)  # game+no-appid → global; pins _current_appid
        if scope is None:
            return await self._offload_call(
                lambda: self._controller_backend.get_config(self._current_appid))
        cfg = await self._offload_call(
            lambda: self._controller_backend.set_button(source, targets, scope, appid))
        self._last_controller_overrides = self._controller_backend.effective_overrides(
            self._current_appid)
        return cfg

    async def set_controller_follow_global(self, follow: bool, appid) -> dict:
        """Toggle a game between its own remap and following the global one, keeping
        its stored overrides (never deletes). Seeds from global on "use own" if it has
        none, then re-applies the now-effective profile (InputPlumber only)."""
        self._init()
        if appid is not None:
            appid = str(appid)
            self._current_appid = appid  # pin so the re-apply/state use the toggled game
            if not follow and not self._controller_backend.has_game(appid):
                self._controller_backend.create_game_from_global(appid)  # already sets follow_global=False
            else:
                self._controller_backend.set_follow_global(appid, bool(follow))
            self._reapply_controller()
        return await self._offload_call(
            lambda: self._controller_backend.get_config(self._current_appid))

    async def set_controller_setting(self, field: str, value: str) -> dict:
        """Change a controller setting on HHD (mode / paddles_as; no-op on others)."""
        self._init()
        return await self._offload_call(
            lambda: self._controller_backend.set_setting(field, value))

    async def reset_controller(self, scope: str = "global", appid=None) -> dict:
        """Reset a scope's remap to the device default (InputPlumber; no-op on others)."""
        self._init()
        scope = self._resolve_scope(scope, appid)
        if scope is None:
            return await self._offload_call(
                lambda: self._controller_backend.get_config(self._current_appid))
        cfg = await self._offload_call(
            lambda: self._controller_backend.reset(scope, appid))
        self._last_controller_overrides = self._controller_backend.effective_overrides(
            self._current_appid)
        return cfg

    def _reapply_controller(self) -> None:
        """On a game change, load the effective InputPlumber profile for the running
        game — but only when it DIFFERS from what's already loaded, so the common case
        (following global, or the same profile) never touches the daemon and can't
        race its own re-grab on game launch. Offloaded (dbus + YAML subprocess). No-op
        on HHD/none (effective_overrides returns None)."""
        if not self._module_enabled("mandos"):
            return
        ov = self._controller_backend.effective_overrides(self._current_appid)
        if ov is None or ov == self._last_controller_overrides:
            return
        # No remaps configured and none ever applied this session → leave the daemon
        # untouched (don't reset it to default just because a game launched).
        if not ov and self._last_controller_overrides is None:
            return
        appid = self._current_appid

        def apply():
            if self._controller_backend.apply_effective(appid):
                self._last_controller_overrides = ov

        self._offload(apply)

    # ---- Ajustes: per-game profile overview --------------------------------
    def _scoped_stores(self):
        """Every store that keeps per-game profiles, all sharing list_games/forget_game
        (the controller backend no-ops when it's not InputPlumber)."""
        return (self._tdp_profiles, self._fan_curves, self._color, self._cpu_profiles,
                self._audio_eq, self._controller_backend)

    def _game_profile_row(self, appid: str) -> dict:
        """A game's per-section profiles for the overview — RAW own values (what the user
        set), not the effective/global-inherited ones. A section is included only when
        the game's own profile actually DIFFERS from global (a bare scope-toggle that
        just copied global isn't 'configured'); `follows_global` marks a
        configured-but-inactive one."""
        row = {"appid": appid}
        if self._tdp_profiles.differs_from_global(appid):
            tp = self._tdp_profiles.game_profile(appid)
            row["tdp"] = {"pl1": int(tp.get("pl1", 0)),
                          "auto": bool(tp.get("auto_tdp")),
                          "gpu": bool((tp.get("gpu") or {}).get("manual")),
                          "follows_global": self._tdp_profiles.is_following_global(appid)}
        if self._fan_curves.differs_from_global(appid):
            row["fan"] = {"preset": self._fan_curves.game_profile(appid).get("preset", "auto"),
                          "follows_global": self._fan_curves.is_following_global(appid)}
        if self._color.differs_from_global(appid):
            cp = self._color.game_profile(appid)
            row["color"] = {"saturation": int(cp.get("saturation", 100)),
                            "calibrated": any(cp.get(f) != COLOR_NATIVE[f] for f in COLOR_CALIBRATION),
                            "hdr": bool(cp.get("hdr")),
                            "follows_global": self._color.is_following_global(appid)}
        if self._cpu_profiles.differs_from_global(appid):
            up = self._cpu_profiles.game_profile(appid)
            row["cpu"] = {"smt": bool(up.get("smt", True)),
                          "boost": bool(up.get("boost", True)),
                          "cores": up.get("cores"),
                          "follows_global": self._cpu_profiles.is_following_global(appid)}
        if self._controller_backend.differs_from_global(appid):
            row["mandos"] = {"count": len(self._controller_backend.game_profile(appid)),
                             "follows_global": self._controller_backend.is_following_global(appid)}
        if self._audio_eq.differs_from_global(appid):
            row["audio"] = {"follows_global": self._audio_eq.is_following_global(appid)}
        return row

    async def list_game_profiles(self) -> list:
        """Every game with a per-game profile that differs from global in ANY section, for
        the Ajustes overview. The frontend resolves names + formats the summaries (i18n)."""
        self._init()
        appids = set()
        for store in self._scoped_stores():
            appids.update(store.list_games())
        rows = (self._game_profile_row(a) for a in sorted(appids))
        return [r for r in rows if len(r) > 1]  # drop games whose every section == global

    async def reset_game_profiles(self, appid) -> list:
        """Forget a game's per-section profiles across every store → it reverts to
        global. Re-applies if it's the running game. Returns the refreshed list."""
        self._init()
        appid = str(appid)
        for store in self._scoped_stores():
            store.forget_game(appid)
        if appid == self._current_appid:
            self._reapply_all()
        return await self.list_game_profiles()

    async def get_controller_conflict(self) -> dict:
        self._init()
        hhd_present = self._controller_backend.manager == controller_detect.HHD
        # Only read HHD state when HHD is the active manager (its API is local).
        state = controller_hhd.read_state() if hhd_present else None
        out = controller_conflict.assess(state, self._tdp_backend.supported)
        out["hhd_present"] = hhd_present
        return out

    # ---- TDP conflict + master switch --------------------------------------
    async def get_tdp_conflict(self) -> dict:
        """Whether HHD is currently managing the power rails. SimpleDeckyTDP is
        detected on the frontend (the backend can't see it)."""
        self._init()
        hhd_present = self._controller_backend.manager == controller_detect.HHD
        # current_tdp_enable does a blocking HTTP GET; the frontend polls this, so
        # keep it off the event loop.
        managing = (await self._offload_call(controller_hhd.current_tdp_enable) or False) \
            if hhd_present else False
        return {"hhd_present": hhd_present, "hhd_managing": bool(managing)}

    async def take_tdp_control(self) -> dict:
        """Hand HHD's TDP module over to us (reversible), saving its previous value.
        ok only when the echo confirms it's off."""
        self._init()
        # HHD's REST client is blocking urllib — keep it off the loop.
        prev = await self._offload_call(controller_hhd.current_tdp_enable)
        if prev is None:
            return {"ok": False, "hhd_managing": False}
        if prev and self._settings.get("hhd_tdp_prev") is None:
            self._settings["hhd_tdp_prev"] = True
        applied = await self._offload_call(lambda: controller_hhd.set_tdp_enable(False))
        self._save()
        await self._offload_call(self._reapply_tdp)
        return {"ok": applied is False, "hhd_managing": bool(applied)}

    def _restore_hhd_tdp(self) -> None:
        """Return HHD to its previous tdp_enable if we took it. Idempotent. Clears the
        marker only once the write confirms, so a failed hand-back is retried later."""
        try:
            prev = self._settings.get("hhd_tdp_prev")
            if prev is None:
                return
            echoed = controller_hhd.set_tdp_enable(bool(prev))
            if echoed != bool(prev):
                return  # unreachable/mismatch → keep the marker to retry
            self._settings["hhd_tdp_prev"] = None
            self._save()
        except Exception:  # noqa: BLE001
            pass

    async def get_tdp_control_enabled(self) -> bool:
        self._init()
        return self._tdp_control_on()

    async def set_tdp_control_enabled(self, enabled: bool) -> bool:
        """OFF = stop writing rails and hand HHD back (step aside). ON = re-assert
        our setpoint."""
        self._init()
        enabled = bool(enabled)
        self._settings["tdp_control_enabled"] = enabled
        self._save()
        if not enabled:
            await self._offload_call(self._restore_hhd_tdp)
        else:
            await self._offload_call(self._reapply_tdp)
        return enabled

    async def set_seen_autotdp_notice(self, seen: bool) -> bool:
        self._init()
        self._settings["seen_autotdp_notice"] = bool(seen)
        self._save()
        return bool(seen)

    async def set_seen_tdp_conflict_takeover(self, seen: bool) -> bool:
        self._init()
        self._settings["seen_tdp_conflict_takeover"] = bool(seen)
        self._save()
        return bool(seen)

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
        # Some kernels load lenovo_wmi_other but publish no hwmon fan node — read the
        # RPM straight from the EC so the monitor still shows the fan.
        if not state["fans"] and self._ec_rpm is not None:
            try:
                rpm = self._ec_rpm.read_rpm()
                if rpm is not None and rpm > 0:
                    state = {**state, "supported": True,
                             "fans": [{"label": "fan", "rpm": rpm, "percent": None}]}
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
        """Push the effective fan curve off the event loop (Steam Deck's software-loop
        backend spawns a blocking systemctl). `done` (re)starts the curve loop on the
        event loop after the apply took ownership — race-free (see _ensure_fan_loop)."""
        self._offload(self._reapply_fans_sync, done=self._ensure_fan_loop)

    def _ensure_fan_loop(self) -> None:
        """Start a software-loop backend's periodic curve loop ON the event loop.
        Applies run off-loop (worker thread, no loop) where the backend's own start()
        no-ops — so the loop that re-evaluates the curve against live temperature (and
        enforces the high-temp guardian) would never run. Call after an apply has taken
        fan ownership (race-free via _offload's `done`). No-op for backends without a
        loop and when not driving (auto mode)."""
        ctrl = self._fan_ctrl
        starter = getattr(ctrl, "start", None)
        if callable(starter) and getattr(ctrl, "_owns_fan", False):
            try:
                starter()
            except Exception:  # noqa: BLE001 — starting the loop must never break an RPC
                pass

    def _reapply_fans_sync(self) -> bool:
        """Apply the effective fan profile for the current game (or global). Returns
        whether the intended state was established (the apply/release reported ok) so
        callers that care — the reset — don't claim success on a refused re-apply.

        - auto      -> firmware control.
        - adaptive  -> drive the LEARNED curve (computed live from telemetry): the
                       balanced fit biased by the scope's silence↔cool dial. When
                       there isn't enough real data yet, fall back to firmware auto
                       (never fabricate a curve) — the card shows the learning state.
        - preset/custom -> write the stored 8-point curve to all fans.

        Guarded: a bad fan apply must never brick load.
        """
        if not self._module_enabled("fanControl"):
            # Fan control disabled: hand the fans back to firmware auto, never drive.
            self._restore_fans_safe()
            return True
        if getattr(self, "_fan_max", False):
            # Keep full-blast across game changes / re-fits; a curve re-apply would
            # silently end it and leave the reported state lying.
            set_max = getattr(self._fan_ctrl, "set_max", None)
            if callable(set_max):
                res = set_max(True)
                return bool(res.get("ok")) if isinstance(res, dict) else False
        try:
            profile = self._fan_curves.effective(self._current_appid)
            preset = profile["preset"]
            if preset == "adaptive":
                points = self._adaptive_curve_points(self._current_appid)
                if points is None:
                    res = self._fan_ctrl.set_auto(None)  # not enough data → firmware auto
                else:
                    res = self._fan_ctrl.apply_curve_all(points)
            elif preset == "auto" or not profile["points"]:
                res = self._fan_ctrl.set_auto(None)
            else:
                res = self._fan_ctrl.apply_curve_all(profile["points"])
            # A malformed response (None / {} / no "ok") is not success, so reset_ok
            # can't ride a bad re-apply.
            return bool(res.get("ok")) if isinstance(res, dict) else False
        except Exception:  # noqa: BLE001
            return False

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
        # A device that can't be controlled but exposes its firmware curve (MSI Claw)
        # shows it read-only, as [{temp, pct}]. Never activates when a write backend
        # is present; None everywhere else (the reader is cached, static config).
        firmware_points = None
        if not hw_state.get("supported") and self._ec_curve is not None:
            curve = self._ec_curve.read_curve()
            if curve:
                firmware_points = [{"temp": t, "pct": p} for t, p in curve]
        return {
            "supported": hw_state.get("supported", False),
            "resettable": bool(getattr(self._fan_ctrl, "resettable", False)),
            "firmware_points": firmware_points,
            "source": hw_state.get("source"),
            "pwm_max": hw_state.get("pwm_max", 255),
            "preset": effective["preset"],
            "points": effective["points"],
            "bias": effective.get("bias", 0),
            "global_preset": global_curve["preset"],
            "global_points": global_curve["points"],
            "has_game_profile": (self._current_appid is not None
                                 and self._fan_curves.has_game(self._current_appid)),
            "follows_global": self._fan_curves.is_following_global(self._current_appid),
            "appid": self._current_appid,
            "presets": [{"id": pid, "points": pts}
                        for pid, pts in fan_presets.RESOLVED.items()],
            # Experimental EC control (Legion Go S): available = device has the
            # unofficial channel; enabled = the user opted in.
            "experimental_available": getattr(self, "_fan_experimental_available", False),
            "experimental_enabled": bool(self._settings.get("fan_experimental", False)),
            "os_name": self._os_name,
            # Active firmware mode governing the fan; None = custom / no firmware modes.
            "firmware_mode": (fw if (fw := self._firmware_mode()) != _CUSTOM_MODE else None),
            "has_firmware_modes": bool(self._firmware_choices()),
            # Full-blast override ("a tope"): available only where the backend exposes it.
            "max_available": bool(getattr(self._fan_ctrl, "supports_max", False)),
            "max_enabled": bool(getattr(self, "_fan_max", False)),
        }

    async def _prime_firmware_curve(self) -> None:
        """Read the EC firmware curve off the event loop (modprobe + EC handshake can
        block). Cached in the reader, so this is a one-time cost; _fan_curve_state
        then reads the cached value without blocking. No-op when there's no reader."""
        if self._ec_curve is not None and not self._fan_ctrl.supported:
            await asyncio.to_thread(self._ec_curve.read_curve)

    async def _prime_fan_backend(self) -> None:
        """Off-loop one-time probe for backends that must modprobe/handshake before a
        clean on-loop read_state (Legion GZFD via acpi_call). No-op otherwise."""
        primer = getattr(self._fan_ctrl, "prime", None)
        if callable(primer):
            await asyncio.to_thread(primer)

    async def get_fan_curve_state(self) -> dict:
        self._init()
        await self._prime_firmware_curve()
        await self._prime_fan_backend()
        return self._fan_curve_state()

    async def get_fan_max(self) -> bool:
        self._init()
        return bool(getattr(self, "_fan_max", False))

    async def set_fan_max(self, enabled: bool) -> dict:
        """Toggle the manual full-blast override. On → drive the backend to max off the
        loop; off → clear it and revert to the effective curve. Session state (not
        persisted); physically released on unload via _restore_fans_safe."""
        self._init()
        enabled = bool(enabled)
        set_max = getattr(self._fan_ctrl, "set_max", None)
        if not callable(set_max):
            return self._fan_curve_state()   # backend can't drive max; nothing to do
        self._fan_max = enabled
        if enabled:
            await self._offload_call(lambda: set_max(True))
        else:
            await self._offload_call(lambda: set_max(False))
            self._reapply_fans()   # back to the curve / firmware auto
        return self._fan_curve_state()

    async def set_fan_experimental(self, enabled: bool) -> dict:
        """Opt in/out of experimental EC fan control (Legion Go S). The swap probes
        sysfs (backend selection) + drives the EC, so it runs OFF the event loop to
        keep the QAM render fluid; only the small state read stays on the loop."""
        self._init()
        enabled = bool(enabled)
        self._settings["fan_experimental"] = enabled
        self._store.save(self._settings)
        await self._offload_call(lambda: self._swap_fan_backend(enabled))
        self._ensure_fan_loop()  # swap ran off-loop; start the curve loop here
        return self._fan_curve_state()

    def _swap_fan_backend(self, enabled: bool) -> None:
        """Release the current backend (never leave the fan driven), rebuild it for
        the new experimental flag, and re-apply the effective curve. Off-loop."""
        try:
            self._fan_ctrl.restore_auto()  # hand any active EC drive back to firmware
        except Exception:  # noqa: BLE001 — release is best-effort; must not raise
            pass
        self._fan_ctrl = fan_control.select_fan_backend(
            self._device, temp_fn=self._driving_temp, experimental=enabled)
        self._reapply_fans_sync()

    async def set_fan_follow_global(self, follow: bool, appid) -> dict:
        """Toggle a game between its own fan curve and following the global one, keeping
        its stored curve (never deletes). Seeds from global on "use own" if it has none."""
        self._init()
        if appid is not None:
            appid = str(appid)
            self._current_appid = appid  # pin so the re-apply/state use the toggled game
            if not follow and not self._fan_curves.has_game(appid):
                self._fan_curves.create_game_from_global(appid)
            self._fan_curves.set_follow_global(appid, bool(follow))
            self._reapply_fans()
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

    async def reset_fan_control(self) -> dict:
        """Recover a wedged software-loop fan control: hand the fan back to firmware
        (off the event loop), then re-establish the stored curve and read the state
        back. `reset_ok` reflects whether the release actually landed — a malformed or
        failed response is not success."""
        self._init()
        try:
            res = await self._offload_call(self._fan_ctrl.restore_auto)
            released = bool(res.get("ok")) if isinstance(res, dict) else False
        except Exception:  # noqa: BLE001
            released = False
        # Re-establish the stored curve off-loop, then restart the curve loop, before
        # reading the state back. reset_ok requires BOTH the release and the re-apply.
        reapplied = await self._offload_call(self._reapply_fans_sync)
        self._ensure_fan_loop()
        state = self._fan_curve_state()
        state["reset_ok"] = released and bool(reapplied)
        return state

    # ---- Fan-curve suggestion (suggestion brain over local telemetry) -------
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
        if not self._learning_active():
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
        """Drive the learned curve when the effective mode is Adaptive.

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
        never walked otherwise. Never raises; never applies a fabricated curve."""
        try:
            appid = self._current_appid
            if appid is None or not self._fan_curves.is_adaptive(appid):
                return
            points = self._adaptive_curve_points(appid)
            if points is None:
                return  # not enough real data yet → firmware auto stays
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
        """Periodically (every ~30 min of play) re-fit and re-drive the adaptive
        curve so it follows the game's RECENT thermal pattern (the histogram decays)."""
        self._drive_adaptive_fan_curve(reapply=True)

    # ---- Telemetry ----------------------------------------------------------
    def _collect_sample(self):
        """Build one telemetry sample from live readers.

        Returns (appid, sample_dict) while in-game, or None when idle.
        Never raises; any error degrades to None (no sample recorded).
        """
        if not self._learning_active():
            return None
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
        """Sampler callback after each stored sample (re-apply cadence).

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

    def _sync_sampler(self) -> None:
        """Start the sampler iff learning is effectively active (enabled AND a consumer
        — Power or Fans — is on), else stop it. Called when module state changes."""
        if getattr(self, "_sampler", None) is None:
            return
        if self._learning_active():
            self._start_sampler()
        else:
            self._sampler.stop()

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
        self._sync_sampler()  # honours the Power/Fans dependency (also flushes on stop)
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
        await self._offload_call(self._reapply_tdp)
        return enabled

    async def get_cooler_boost(self) -> bool:
        self._init()
        return bool(self._settings.get("cooler_boost", False))

    async def set_cooler_boost(self, enabled: bool) -> bool:
        """Opt in/out of the GPD Win 5 cooler-attached ceiling. Re-applies TDP so the
        new ceiling (and any re-clamp of the current setpoint) takes effect now."""
        self._init()
        enabled = bool(enabled)
        self._settings["cooler_boost"] = enabled
        self._save()
        await self._offload_call(self._reapply_tdp)
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
        real in-game value on its next tick (no jarring drop)."""
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
        (a 35 W cap with the GPU at 80% would hold at max forever). The learned
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
                # TDP master switch off (module 'power') or Auto-TDP disabled — don't
                # drive PL1. _module_enabled folds the power cascade into autoTdp.
                if not self._module_enabled("autoTdp"):
                    self._reset_auto_windows()
                    continue
                # Hold when auto-TDP is off for THIS game (per-game, own or global) or a
                # named firmware mode owns the rails — either way we don't drive PL1.
                if (not self._tdp_profiles.auto_tdp(self._current_appid)
                        or self._firmware_mode() != _CUSTOM_MODE):
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
                    await self._offload_call(self._reapply_tdp)
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
        or when not auto / no game / UI closed. Don't claim a raise that
        isn't happening."""
        if not (self._qam_boost_active() and self._current_appid is not None
                and self._tdp_profiles.auto_tdp(self._current_appid)):
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
        auto = self._tdp_profiles.auto_tdp(self._current_appid)
        ac = read_on_ac()
        setpoint = self._effective_levels(self._current_appid, ac)[0]["pl1"]
        # Live PL1 the firmware holds (reflects eco + external HHD/Steam changes). Skip
        # it on subprocess-backed backends (ryzenadj) so the 1 s poll doesn't fork a
        # tool every tick — the arc falls back to the setpoint there.
        applied = None if getattr(self._tdp_backend, "blocking", False) else await self._read_applied()
        return {
            "watts": pr["watts"],
            "gpu_busy": pr["gpu_busy"],
            "auto_tdp": auto,
            "setpoint": setpoint,
            "applied": applied,
            "ui_floor_engaged": self._ui_floor_engaged(),
            # Polled every second, so the UI can refresh the slider ceiling the moment
            # the charger is plugged or unplugged.
            "on_ac": ac,
        }

    async def set_auto_tdp(self, enabled: bool, scope: str = "global", appid=None) -> dict:
        self._init()
        if not self._tdp_control_on():
            return {"auto_tdp": self._tdp_profiles.auto_tdp(self._current_appid)}
        self._clear_eco()
        self._tdp_profiles.set_auto_tdp(scope, bool(enabled), appid=appid)
        await self._offload_call(self._reapply_tdp)
        return {"auto_tdp": self._tdp_profiles.auto_tdp(self._current_appid)}

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
                and self._tdp_profiles.auto_tdp(self._current_appid)
                and self._firmware_mode() == _CUSTOM_MODE):
            lim = self._limits()
            floor = auto_tdp.effective_floor(lim.min_w, True)
            cur = self._effective_levels(self._current_appid)[0]["pl1"]
            if cur < floor:  # only raise if actually below the responsive floor
                self._tdp_profiles.set_pl1(self._auto_scope(), floor,
                                           appid=self._current_appid)
                await self._offload_call(self._reapply_tdp)
                self._clear_auto_windows()  # PL1 changed → window is now stale
        return self._ui_active

    # ---- TDP helpers + RPCs -------------------------------------------------
    def _limits(self):
        """Device TDP limits with the user's opt-in ceilings applied (a single
        chokepoint so every clamp/limit path honours the Ajustes toggles): the
        battery-unlock preference, then the GPD Win 5 cooler boost."""
        # Chokepoint for the battery-unlock preference. Ignore it where the firmware
        # enforces the battery cap (Ally/Ally X) — the write would be refused, so the
        # reported ceiling must not claim the extra either.
        unlock = (bool(self._settings.get("unlock_battery_max", False))
                  and not self._device.charger_only_extra)
        lim = self._tdp_backend.get_limits().unlocked(unlock)
        cooler_max = self._device.cooler_max
        if cooler_max and self._settings.get("cooler_boost", False):
            lim = lim.with_cooler(cooler_max)
        return lim

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

    # ---- Learned TDP band ---------------------------------------------------
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

        if not self._learning_active():
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
        """The TDP profile scope the auto machinery writes to. Only the game scope when
        the running game has its OWN profile; a game that follows global is tuned via the
        global profile it inherits, so the loop never silently detaches it (which would
        flip follow_global off and mint a per-game profile with no user action)."""
        appid = self._current_appid
        if appid is not None and not self._tdp_profiles.is_following_global(appid):
            return "game"
        return "global"

    # ---- off-loop dispatch --------------------------------------------------
    # Any subprocess/HTTP-backed apply (gamescopectl, systemctl, ryzenadj, …) MUST
    # run through one of these so a wedged tool can't stall the event loop that
    # drives the auto-TDP loop + every QAM RPC. The single-worker executor (created
    # in _main) serialises applies → no race on shared state (e.g. the color LUT
    # file). No executor / no loop (unit tests) → run inline (behaviour preserved).
    def _offload(self, fn, done=None):
        """Fire-and-forget a blocking apply off the event loop. Guards fn on both
        paths so a raise can't kill the caller nor leak an unretrieved-future log.

        `done` (optional) runs ON the event loop AFTER fn finishes — use it to start
        work that depends on state fn just set (e.g. a re-assert loop that needs the
        apply to have taken fan ownership first), race-free. It must be safe to run
        on the loop; it is guarded like fn."""
        def guarded():
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

        def run_done(*_):
            try:
                done()
            except Exception:  # noqa: BLE001
                pass

        ex = getattr(self, "_apply_executor", None)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if ex is None or loop is None:
            guarded()
            if done is not None:
                run_done()
        else:
            fut = loop.run_in_executor(ex, guarded)
            if done is not None:
                fut.add_done_callback(run_done)

    async def _offload_call(self, fn):
        """Run a blocking call off the event loop and return its result (awaited).
        Falls back to a default worker thread when the serial executor isn't up yet
        (before _main / after shutdown) so blocking work — systemctl, EC writes — never
        lands on the loop."""
        ex = getattr(self, "_apply_executor", None)
        if ex is None:
            return await asyncio.to_thread(fn)
        return await asyncio.get_running_loop().run_in_executor(ex, fn)

    async def _drain_offloaded(self):
        """Wait for the queued off-loop applies to finish (a no-op runs after them on
        the single-worker executor). Use before reading back hardware state that a
        fire-and-forget apply just changed, so the readback isn't stale."""
        ex = getattr(self, "_apply_executor", None)
        if ex is None:
            return
        await asyncio.get_running_loop().run_in_executor(ex, lambda: None)

    def _firmware_choices(self) -> list:
        """Firmware performance modes the device exposes, or [] when it has none."""
        return self._tdp_backend.profile_choices() if self._device.firmware_modes else []

    def _firmware_mode(self) -> str:
        """Selected firmware performance mode on a device that exposes them
        ('low-power'/'balanced'/'performance'), else 'custom' (our TDP owns the rails)."""
        if not self._device.firmware_modes:
            return _CUSTOM_MODE
        return self._settings.get("firmware_mode") or _CUSTOM_MODE

    def _exit_firmware_mode(self) -> None:
        """A manual TDP action (slider / boost offsets) returns control to our TDP."""
        if self._firmware_mode() != _CUSTOM_MODE:
            self._settings["firmware_mode"] = _CUSTOM_MODE
            self._save()

    def _tdp_control_on(self) -> bool:
        """Master switch: whether we're allowed to write the TDP rails at all."""
        return bool(self._settings.get("tdp_control_enabled", True))

    # ---- Module enable/disable ---------------------------------------------
    # autoTdp/fanControl cascade from their tab (all); learning needs a consumer (any).
    # MIRROR of REQUIRES in src/customize/moduleLogic.ts — keep the two in sync.
    _MODULE_REQUIRES = {
        "autoTdp": ("all", ("power",)),
        "fanControl": ("all", ("fans",)),
        "learning": ("any", ("power", "fans")),
    }
    _GENERIC_MODULES = ("system", "display", "fans", "mandos", "autoTdp", "fanControl")
    # Modules backed by a pre-existing boolean setting instead of disabled_modules
    # (setting True = module enabled). Single source of truth per concept.
    _MODULE_SETTING = {"power": "tdp_control_enabled", "learning": "telemetry_enabled"}

    def _disabled_modules(self) -> list:
        v = self._settings.get("disabled_modules")
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    def _module_user_disabled(self, mid: str) -> bool:
        """Whether the user turned this module off (before cascade/dependency)."""
        setting = self._MODULE_SETTING.get(mid)
        if setting is not None:
            return not bool(self._settings.get(setting, True))
        return mid in self._disabled_modules()

    def _module_enabled(self, mid: str) -> bool:
        """Effective state: user flag AND requirements (cascade = all, dependency = any)."""
        if self._module_user_disabled(mid):
            return False
        req = self._MODULE_REQUIRES.get(mid)
        if not req:
            return True
        mode, ids = req
        checks = [self._module_enabled(d) for d in ids]
        return any(checks) if mode == "any" else all(checks)

    def _learning_active(self) -> bool:
        """Learning runs only when enabled AND it has a consumer (Power or Fans)."""
        return self._module_enabled("learning")

    def _user_disabled_all(self) -> list:
        """The user-disabled set (for the UI), folding the native-setting modules in."""
        out = list(self._disabled_modules())
        for mid, setting in self._MODULE_SETTING.items():
            if not bool(self._settings.get(setting, True)):
                out.append(mid)
        return out

    def _reapply_tdp(self, on_ac=None):
        self._init()
        if not self._tdp_control_on():
            # Master switch off: we've handed the rails to another tool. Don't write.
            self._last_written_pl1 = None
            return TdpResult(None, None, True, "tdp-control-disabled")
        mode = self._firmware_mode()
        if mode != _CUSTOM_MODE:
            # A named firmware mode owns the rails, fan curve and LED — don't force custom.
            self._tdp_backend.set_profile(mode)
            self._last_written_pl1 = None
            return TdpResult(None, self._tdp_backend.read_applied(), True, f"firmware-mode:{mode}")
        lv, _active, ac = self._effective_levels(self._current_appid, on_ac)
        res = self._tdp_backend.set_levels(lv["pl1"], lv["pl2"], lv["pl3"], ac)
        # Record what the firmware now holds (readback), so adoption can tell a real
        # external change from our own write.
        self._last_written_pl1 = res.applied_w if res.applied_w is not None else lv["pl1"]
        return res

    def _reapply_all(self, on_ac=None) -> None:
        """Lifecycle callback: re-assert TDP, the fan curve, the charge limit and the
        CPU controls (resume/AC — firmware may drop these across a suspend)."""
        # A context change (resume, AC/DC, game change, eco) invalidates any
        # unconfirmed calibration preview — drop it and cancel its revert timer so a
        # stale preview can't leak onto the new context (nor a dangling timer fire).
        self._cancel_color_revert()
        self._color_preview = None
        # A context change is landing (resume/AC/game/eco) — the firmware may be mid-
        # transition until the offloaded re-apply below writes. Suspend adoption until
        # then so a transient/default read isn't mistaken for an external change.
        self._last_written_pl1 = None
        # sysfs (fast) → inline; subprocess-backed (tdp-ryzenadj/fans/color) → off-loop.
        self._apply_charge_limit()
        self._apply_cpu()
        self._apply_gpu_clock()
        self._offload(lambda: self._reapply_tdp(on_ac))
        # Stepped aside: retry a pending HHD hand-back (no-op while we control / no marker).
        if not self._tdp_control_on():
            self._offload(self._restore_hhd_tdp)
        self._reapply_fans()   # self-offloading
        # HDR before color: switching the HDR mode can drop the loaded LUT, so re-assert
        # HDR first and load the color look after (both self-offloading, FIFO executor).
        self._reapply_hdr()
        self._reapply_color()
        self._reapply_audio()  # self-offloading; no-op when the EQ is disabled
        self._reapply_controller()  # diff-gated; no-op unless the effective remap changed

    # ---- Battery + charge limit --------------------------------------------
    def _apply_charge_limit(self) -> None:
        """Write the persisted charge limit (or 100 = no cap when disabled). Safe to
        call on any device — a Null backend no-ops."""
        if not self._charge_limit.supported:
            return
        if not self._module_enabled("system"):
            # Module off = step aside: release any cap, don't keep limiting.
            self._charge_limit.disable()
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
            # report what the firmware actually holds (it may clamp our write).
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
        """Re-assert the persisted core count, SMT + boost state (safe no-op where
        unsupported). In download mode, boost is forced off regardless of the saved
        setting.

        ORDER MATTERS: cores FIRST (onlining the kept cores brings their SMT siblings
        online too), then SMT — so SMT-off re-offlines those siblings and the two
        controls, which write the same cpuN/online nodes, end up consistent."""
        if not self._module_enabled("system"):
            # Module off = step aside: hand the CPU back to its defaults (all cores
            # online, SMT on, boost on) instead of leaving it as we last set it.
            if self._cores.supported and self._cores.max_cores is not None:
                self._cores.set(int(self._cores.max_cores))
            if self._smt.supported:
                self._smt.set(True)
            if self._boost.supported:
                self._boost.set(True)
            return
        # Effective per-game CPU controls (own when the game has them, else global).
        eff = self._cpu_profiles.effective(self._current_appid)
        # Re-assert the active-core count. None = "all cores" → actively restore the full
        # count (so switching FROM a core-limited game/global back to an unlimited scope
        # brings the offlined cores back, instead of leaving them off).
        if self._cores.supported:
            n = eff["cores"] if eff["cores"] is not None else self._cores.max_cores
            if n is not None:
                self._cores.set(int(n))
        if self._smt.supported:
            self._smt.set(bool(eff["smt"]))
        if self._boost.supported:
            eco = self._settings.get("eco_enabled", False)
            self._boost.set(False if eco else bool(eff["boost"]))

    def _clear_eco(self) -> None:
        """Manual control taken → exit download mode and restore the normal TDP/boost
        state. Brightness is NOT touched here (FE-only; the persistent controller
        stops driving it and the user keeps whatever they set)."""
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
            # Active physical cores (None max = feature unavailable on this device).
            "cores_supported": self._cores.supported,
            "max_cores": self._cores.max_cores,
            "active_cores": self._cores.active() if self._cores.supported else None,
            "follows_global": self._cpu_profiles.is_following_global(self._current_appid),
            "has_game_profile": (self._current_appid is not None
                                 and self._cpu_profiles.has_game(self._current_appid)),
        }

    async def get_cpu_state(self) -> dict:
        self._init()
        return self._cpu_state()

    async def set_active_cores(self, count: int, scope: str = "global", appid=None) -> dict:
        self._init()
        self._clear_eco()
        self._cpu_profiles.set_cores(scope, int(count), appid=appid)
        self._apply_cpu()  # orders cores→SMT so kept cores' SMT siblings don't re-online
        return self._cpu_state()

    async def set_cpu_follow_global(self, follow: bool, appid) -> dict:
        """Toggle a game between its own CPU controls (SMT/boost/cores) and following the
        global ones, keeping its stored values (never deletes). Seeds from global on use-own."""
        self._init()
        if appid is not None:
            appid = str(appid)
            self._current_appid = appid  # pin so the re-apply/state use the toggled game
            if not follow and not self._cpu_profiles.has_game(appid):
                self._cpu_profiles.create_game_from_global(appid)
            self._cpu_profiles.set_follow_global(appid, bool(follow))
            self._apply_cpu()
        return self._cpu_state()

    # ---- GPU clock (Potencia) ----------------------------------------------
    def _apply_gpu_clock(self) -> None:
        """Re-assert the GPU clock window when manual (cleared to auto after suspend).
        When not manual we leave the GPU alone (don't fight other tools). Guarded."""
        if not self._module_enabled("power"):
            return
        try:
            g = self._tdp_profiles.gpu_clock(self._current_appid)  # effective per game
            if not self._gpu_clock.supported or not g.get("manual"):
                return
            lo, hi = g.get("min"), g.get("max")
            if lo is not None and hi is not None:
                self._gpu_clock.set(int(lo), int(hi))
        except Exception:  # noqa: BLE001
            pass

    def _gpu_clock_state(self) -> dict:
        g = self._tdp_profiles.gpu_clock(self._current_appid)
        rng = self._gpu_clock.get_range()
        cur = self._gpu_clock.get()
        gmin, gmax = g.get("min"), g.get("max")
        return {
            "supported": self._gpu_clock.supported,
            "manual": bool(g.get("manual")),
            "range_min": rng[0] if rng else None,
            "range_max": rng[1] if rng else None,
            # Stored per-scope window when set; else the live/full range for the sliders.
            "min": gmin if gmin else (cur[0] if cur else (rng[0] if rng else None)),
            "max": gmax if gmax else (cur[1] if cur else (rng[1] if rng else None)),
        }

    async def get_gpu_clock(self) -> dict:
        self._init()
        return self._gpu_clock_state()

    async def set_gpu_clock(self, min_mhz: int, max_mhz: int, scope: str = "global", appid=None) -> dict:
        self._init()
        self._tdp_profiles.set_gpu_clock(scope, True, int(min_mhz), int(max_mhz), appid=appid)
        self._apply_gpu_clock()
        return self._gpu_clock_state()

    async def set_gpu_clock_auto(self, scope: str = "global", appid=None) -> dict:
        self._init()
        self._tdp_profiles.set_gpu_clock(scope, False, 0, 0, appid=appid)
        if self._gpu_clock.supported:
            self._gpu_clock.set_auto()
        return self._gpu_clock_state()

    async def set_smt(self, enabled: bool, scope: str = "global", appid=None) -> dict:
        self._init()
        self._clear_eco()
        self._cpu_profiles.set_smt(scope, bool(enabled), appid=appid)
        self._apply_cpu()
        return self._cpu_state()

    async def set_cpu_boost(self, enabled: bool, scope: str = "global", appid=None) -> dict:
        self._init()
        self._clear_eco()
        self._cpu_profiles.set_boost(scope, bool(enabled), appid=appid)
        self._apply_cpu()
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

    # ---- Pantalla (panel color via gamescope) -------------------------------
    def _reapply_color(self) -> None:
        """Push the color apply off the event loop (gamescopectl can stall on a wedged
        compositor). No executor / no loop → inline."""
        self._offload(self._reapply_color_sync)

    def _reapply_color_sync(self) -> None:
        """Push the effective color to gamescope. No-op when unsupported. Guarded.
        Applied in HDR mode too — it colors all composited/SDR content; a native-HDR
        game (direct scanout) is simply out of the LUT's reach, no handling needed."""
        if not self._module_enabled("display"):
            return
        try:
            if self._color_backend.supported:
                self._color_backend.apply(self._effective_color())
        except Exception:  # noqa: BLE001
            pass

    async def _await_display_backend(self, attempts=30, interval=5.0,
                                     reasserts=40, reassert_interval=3.0) -> None:
        """Re-assert the color/HDR look at startup over a short window. gamescope drops a
        look loaded while it is still bringing up the session, so applying once at load
        isn't enough — whether gamescope wasn't up yet when we loaded (cold boot) or it
        was up but still initialising (fast/manual reboot). First wait (bounded) for the
        socket to answer, then re-apply every few seconds across the session-bringup
        window, and finally start the night loop. On a host with no gamescope (desktop)
        it just stays native."""
        try:
            for _ in range(attempts):
                if await self._offload_call(lambda: self._color_backend.supported):
                    break
                await asyncio.sleep(interval)
            else:
                return  # gamescope never came up (desktop) — nothing to apply
            for i in range(reasserts):
                self._reapply_color()
                self._reapply_hdr()
                if i < reasserts - 1:
                    await asyncio.sleep(reassert_interval)
            self._start_night_loop()
        except asyncio.CancelledError:
            pass

    def _display_color(self) -> dict:
        """What the UI reflects: saved effective + the unconfirmed preview. Excludes the
        night-mode shift, so the Temperature slider keeps showing the user's own value."""
        eff = self._color.effective(self._current_appid)
        if self._color_preview is not None:
            eff = {**eff, **self._color_preview}
        return eff

    def _effective_color(self) -> dict:
        """What is pushed to hardware: the displayed color + the night-mode warm shift."""
        eff = self._display_color()
        n = self._night.get()
        if self._night_is_active(n):
            eff = {**eff, "temperature": min(100, eff.get("temperature", 0) + n["warmth"])}
        return eff

    def _night_is_active(self, n=None) -> bool:
        n = n if n is not None else self._night.get()
        return is_night_active(
            _now_minutes(), n["enabled"], n["schedule_enabled"], n["start"], n["end"]
        )

    def _color_state(self) -> dict:
        eff = self._display_color()
        preset_keys = color_presets.preset_keys(self._device)
        return {
            "supported": self._color_backend.supported,
            **{f: eff[f] for f in COLOR_FIELDS},
            "global_saturation": self._color.effective(None)["saturation"],
            "has_game_profile": (self._current_appid is not None
                                 and self._color.has_game(self._current_appid)),
            "follows_global": self._color.is_following_global(self._current_appid),
            "appid": self._current_appid,
            # The per-model "OLED look" preset (None on a real OLED → UI hides the card).
            "oled_look": oled_look_for(self._device),
            "panel": self._device.panel,
            # True when a color look costs a bit of extra power here (Intel forces
            # gamescope composition) → the UI shows an honest, device-named note.
            "perf_cost": getattr(self._color_backend, "force_composite", False),
            "device_name": self._device.display_name,
            # Calibration preview pending confirmation (auto-reverts) + its window.
            "preview": self._color_preview is not None,
            "revert_seconds": self._COLOR_REVERT_SECS,
            "presets": preset_keys,
            "active_preset": self._active_preset(preset_keys),
        }

    def _active_preset(self, keys) -> str:
        """The look key the color actually shown for the current scope matches, or None.
        Compares the effective color (so a per-game saturation override that hides the
        look's saturation correctly reads as custom, not a false match)."""
        cur = self._color.effective(self._current_appid)
        for key in keys:
            preset = color_presets.resolve_preset(self._device, key)
            full = self._color._clean_global(preset or {})  # same merge+clamp apply uses
            if all(cur[f] == full[f] for f in COLOR_FIELDS):
                return key
        return None

    async def get_color_state(self) -> dict:
        self._init()
        return await self._offload_call(self._color_state)

    async def apply_color_preset(self, key: str, scope: str = "global", appid=None) -> dict:
        """Apply a look to the given scope (native = reset that scope). Saved directly."""
        self._init()
        self._cancel_color_revert()
        self._color_preview = None
        preset = color_presets.resolve_preset(self._device, key)
        if key == "native":
            self._color.apply_preset(scope, dict(COLOR_NATIVE), appid=appid)
        elif preset is not None:
            self._color.apply_preset(scope, preset, appid=appid)
        self._reapply_color()
        return await self._offload_call(self._color_state)

    async def set_saturation(self, value: int, scope: str, appid=None) -> dict:
        # Saturation can't make the screen illegible (0 = grayscale) → save directly,
        # no confirm timer.
        self._init()
        self._color.set_saturation(scope, int(value), appid=appid)
        self._reapply_color()
        return await self._offload_call(self._color_state)

    async def set_color_follow_global(self, follow: bool, appid) -> dict:
        """Toggle a game between its own saturation and following the global one, keeping
        its stored value (never deletes). Seeds from global on "use own" if it has none."""
        self._init()
        if appid is not None:
            appid = str(appid)
            self._current_appid = appid  # pin so the re-apply/state use the toggled game
            if not follow and not self._color.has_game(appid):
                self._color.create_game_from_global(appid)
            self._color.set_follow_global(appid, bool(follow))
            self._reapply_color()
        return await self._offload_call(self._color_state)

    async def preview_calibration(self, calibration: dict) -> dict:
        """Apply calibration LIVE without saving, and arm the auto-revert timer. Any
        subset of the calibration fields may be sent; sanitized to the safe ranges so
        the live preview honours the same floors as a saved value. The UI confirms with
        set_calibration; if it doesn't, the screen self-heals."""
        self._init()
        # Empty/malformed payload → nothing to preview: don't arm a revert timer or
        # show a confirm bar with nothing to confirm.
        self._color_preview = sanitize_calibration(calibration) or None
        self._reapply_color()
        if self._color_preview is not None:
            self._arm_color_revert()
        else:
            self._cancel_color_revert()  # empty payload → drop any timer already armed
        return await self._offload_call(self._color_state)

    async def set_calibration(self, calibration: dict, scope: str = "global", appid=None) -> dict:
        """Confirm (save) the calibration for a scope: persist, cancel auto-revert, apply."""
        self._init()
        self._cancel_color_revert()
        self._color_preview = None
        self._color.set_calibration(scope, appid, **sanitize_calibration(calibration))
        self._reapply_color()
        return await self._offload_call(self._color_state)

    def _arm_color_revert(self) -> None:
        self._cancel_color_revert()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop (tests) — the FE countdown still guards the UI
        self._color_revert_task = asyncio.create_task(self._color_revert_after())

    def _cancel_color_revert(self) -> None:
        if self._color_revert_task is not None:
            self._color_revert_task.cancel()
            self._color_revert_task = None

    async def _color_revert_after(self) -> None:
        try:
            await asyncio.sleep(self._COLOR_REVERT_SECS)
            self._do_color_revert()
        except asyncio.CancelledError:
            pass

    def _do_color_revert(self) -> None:
        """Drop the unconfirmed preview and re-apply the saved color."""
        self._color_preview = None
        self._color_revert_task = None
        self._reapply_color()

    async def apply_oled_look(self, scope: str = "global", appid=None) -> dict:
        """One-tap: apply this model's OLED-look preset (calibration + saturation) to the
        given scope. No-op on OLED panels (no preset). Saved directly."""
        self._init()
        self._cancel_color_revert()
        self._color_preview = None
        look = oled_look_for(self._device)
        if look is not None:
            self._color.apply_preset(scope, look, appid=appid)
            self._reapply_color()
        return await self._offload_call(self._color_state)

    async def reset_color(self) -> dict:
        self._init()
        self._cancel_color_revert()
        self._color_preview = None
        self._color.reset()
        self._reapply_color()
        return await self._offload_call(self._color_state)

    # ---- Night mode (scheduled warm shift) ----------------------------------
    def _night_state(self) -> dict:
        n = self._night.get()
        return {
            "supported": self._color_backend.supported,
            **n,
            "active": self._night_is_active(n),
        }

    async def get_night_state(self) -> dict:
        self._init()
        return await self._offload_call(self._night_state)

    async def set_night(self, patch: dict) -> dict:
        """Update night-mode settings (any subset) and re-apply at once."""
        self._init()
        p = patch if isinstance(patch, dict) else {}
        self._night.set(
            warmth=p.get("warmth"), enabled=p.get("enabled"),
            schedule_enabled=p.get("schedule_enabled"),
            start=p.get("start"), end=p.get("end"),
        )
        self._night_applied = self._night_is_active()
        self._start_night_loop()  # idempotent — (re)start if it hadn't come up yet
        self._reapply_color()
        return await self._offload_call(self._night_state)

    def _start_night_loop(self) -> None:
        if not self._color_backend.supported:
            return  # nothing to apply a warm shift to on this host
        if self._night_task is not None and not self._night_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running event loop → skip task creation
        self._night_applied = self._night_is_active()
        self._night_task = asyncio.create_task(self._night_loop())

    def _stop_night_loop(self) -> None:
        if self._night_task is not None:
            self._night_task.cancel()
            self._night_task = None

    async def _night_loop(self) -> None:
        """Re-apply only when the active state crosses a schedule edge."""
        try:
            while True:
                await asyncio.sleep(_NIGHT_TICK_S)
                active = self._night_is_active()
                if active != self._night_applied:
                    self._night_applied = active
                    self._reapply_color()
        except asyncio.CancelledError:
            pass

    # ---- HDR output ----------------------------------------------------------
    def _hdr_supported(self) -> bool:
        return self._device.hdr and self._color_backend.supported

    def _hdr_state(self) -> dict:
        return {
            "supported": self._hdr_supported(),
            "enabled": self._color.hdr(self._current_appid),  # per-game (own or global)
            "follows_global": self._color.is_following_global(self._current_appid),
        }

    def _reapply_hdr(self) -> None:
        # Gate on the effective per-game HDR (skips a no-op executor hop on the common
        # path); the supported probe (may spawn gamescopectl) runs off-loop below.
        if self._color.hdr(self._current_appid):
            self._offload(self._reapply_hdr_sync)

    def _reapply_hdr_sync(self) -> None:
        """Re-assert HDR ON (never force a supported panel OUT of an HDR mode set
        elsewhere, e.g. Steam's own toggle)."""
        try:
            if self._hdr_supported() and self._color.hdr(self._current_appid):
                self._hdr_backend.set_enabled(True)
        except Exception:  # noqa: BLE001
            pass

    async def get_hdr_state(self) -> dict:
        self._init()
        return await self._offload_call(self._hdr_state)

    async def set_hdr(self, patch: dict, scope: str = "global", appid=None) -> dict:
        """Turn HDR on/off for a scope and apply at once (an explicit toggle applies both
        states, unlike the resume re-assert which only re-asserts ON)."""
        self._init()
        p = patch if isinstance(patch, dict) else {}
        if "enabled" in p:
            self._color.set_hdr(scope, bool(p["enabled"]), appid=appid)
        enabled = self._color.hdr(self._current_appid)
        # Off-loop: set_enabled spawns gamescopectl (a no-op when gamescope is absent).
        self._offload(lambda: self._hdr_backend.set_enabled(enabled))
        # Then re-assert the color look — gamescope can drop the loaded LUT on a mode switch.
        self._reapply_color()
        return await self._offload_call(self._hdr_state)

    async def _read_applied(self):
        # Only subprocess-backed backends (ryzenadj fallback) need the executor;
        # sysfs reads (firmware-attr/intel/deck) and acpi-alib (None) are cheap inline.
        b = self._tdp_backend
        if getattr(b, "blocking", False):
            return await self._offload_call(b.read_applied)
        return b.read_applied()

    async def get_tdp_state(self) -> dict:
        self._init()
        applied = await self._read_applied()
        external = self._adopt_external_tdp(applied)
        st = self._tdp_state(applied)
        st["external_change"] = external
        return st

    def _adopt_external_tdp(self, applied) -> bool:
        """Adopt a firmware PL1 moved by an external tool (HHD/Steam) as our setpoint,
        so a later re-apply doesn't stomp it. Compares against the value WE last wrote
        (``_last_written_pl1``): None until our first apply and cleared during a
        re-apply, so a stale/default read at startup or mid-transition never adopts.
        Skipped in eco / auto (we own the setpoint there). True when adopted."""
        if applied is None or self._last_written_pl1 is None:
            return False
        if self._settings.get("eco_enabled") or self._tdp_profiles.auto_tdp(self._current_appid):
            return False
        if abs(int(applied) - int(self._last_written_pl1)) < _EXTERNAL_TDP_THRESHOLD:
            return False
        appid = self._current_appid
        # Adopt into the scope that's actually live (game only when it has its OWN active
        # profile) — never detach a follow-global game that merely kept stored values.
        scope = self._auto_scope()
        self._tdp_profiles.set_pl1(scope, int(applied), appid=appid)
        self._last_written_pl1 = int(applied)
        return True

    def _tdp_state(self, applied_w) -> dict:
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
            # Whether this game is applying the global profile (no own value, or its own
            # is toggled to follow global). Powers the "usa el global / usa el propio" UI.
            "follows_global": self._tdp_profiles.is_following_global(self._current_appid),
            "watts": limits.clamp(eff["watts"], ac),
            "global_watts": limits.clamp(geff["watts"], ac),
            "applied_w": applied_w,
            "supports_advanced": ("pl2" in ll or "pl3" in ll),
            "level_limits": ll,
            "levels": levels,
            "boost_mode": eff["mode"],
            "global_levels": global_levels,
            "global_boost_mode": geff["mode"],
            # The learned band for this game (powers the separate TDP suggestion card).
            # The battery↔performance dial that picks a value inside it is now LOCAL UI
            # state — applying it is a fixed manual setpoint, not a loop parameter.
            "learned": self._tdp_learned_info(self._current_appid),
            "presets": self._tdp_presets(limits),
            # Selectable firmware performance modes; empty on devices without them.
            "firmware_modes": self._firmware_choices(),
            "firmware_mode": self._firmware_mode(),
            # get_tdp_state flips this True when it adopts an external change.
            "external_change": False,
            # Master switch + one-time-notice flags (durable across reboot; the
            # frontend gates monitor-only mode + the first-run modals off these).
            "tdp_control_enabled": self._tdp_control_on(),
            "seen_autotdp_notice": bool(self._settings.get("seen_autotdp_notice", False)),
            "seen_tdp_conflict_takeover": bool(
                self._settings.get("seen_tdp_conflict_takeover", False)),
        }

    def _tdp_presets(self, limits) -> dict:
        """Quick-preset watts for the arc's preset buttons. Curated per-model values
        (device profile) when present, else derived from the rail limits. Clamped to
        the rail so a preset can never sit above the active ceiling."""
        p = self._device.tdp_presets
        if len(p) == 4:
            quiet, balanced, turbo, turbo_ac = p
        else:
            quiet, balanced = limits.min_w, limits.default_w
            turbo, turbo_ac = limits.max_w, limits.max_ac_w
        return {"quiet": limits.clamp(quiet), "balanced": limits.clamp(balanced),
                "turbo": limits.clamp(turbo), "turbo_ac": limits.clamp(turbo_ac)}

    def _resolve_scope(self, scope, appid):
        """Normalize scope/appid; returns scope or None if invalid."""
        if scope not in ("global", "game"):
            return None
        if scope == "game" and appid is None:
            return "global"
        if scope == "game" and appid is not None:
            self._current_appid = str(appid)
        return scope

    @staticmethod
    def _apply_result(res) -> dict:
        return {"requested_w": res.requested_w, "applied_w": res.applied_w,
                "ok": res.ok, "detail": res.detail}

    async def set_tdp_watts(self, watts: int, scope: str, appid=None) -> dict:
        self._init()
        if not self._tdp_control_on():
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": "tdp-control-disabled"}
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        self._clear_eco()  # manual TDP change exits download mode (after scope is valid)
        self._exit_firmware_mode()  # moving the slider means "I want custom"
        limits = self._limits()
        clamped = limits.clamp(watts, read_on_ac())
        self._tdp_profiles.set_pl1(resolved, clamped, appid=appid)
        res = await self._offload_call(self._reapply_tdp)
        return self._apply_result(res)

    async def set_tdp_follow_global(self, follow: bool, appid) -> dict:
        """Toggle a game between its own TDP profile and following the global one,
        keeping its stored values (never deletes). Re-applies and returns full state."""
        self._init()
        if appid is not None:
            self._clear_eco()
            appid = str(appid)
            self._current_appid = appid  # pin so the re-apply/state use the toggled game
            # "Use own" on a game with no profile yet: seed it from the current global so
            # there's an editable starting value (nothing is ever deleted).
            if not follow and not self._tdp_profiles.has_game(appid):
                self._tdp_profiles.create_game_from_global(appid)
            self._tdp_profiles.set_follow_global(appid, bool(follow))
            await self._offload_call(self._reapply_tdp)
        return self._tdp_state(await self._read_applied())

    async def set_tdp_firmware_mode(self, mode: str) -> dict:
        """Select a firmware performance mode (Legion Go original). 'low-power' /
        'balanced' / 'performance' hand power + fan + LED to the firmware; 'custom'
        returns control to our TDP slider. Device-global. Returns the fresh TDP state."""
        self._init()
        if not self._device.firmware_modes:
            return await self.get_tdp_state()
        valid = set(self._firmware_choices()) | {_CUSTOM_MODE}
        if mode not in valid:
            return await self.get_tdp_state()
        self._clear_eco()
        self._settings["firmware_mode"] = mode
        self._save()
        await self._offload_call(self._reapply_tdp)
        return await self.get_tdp_state()

    async def set_tdp_levels(self, off2: int, off3: int, scope: str, appid=None) -> dict:
        self._init()
        if not self._tdp_control_on():
            return {"requested_w": 0, "applied_w": None, "ok": False,
                    "detail": "tdp-control-disabled"}
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": 0, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        self._clear_eco()
        self._exit_firmware_mode()
        self._tdp_profiles.set_offsets(resolved, off2, off3, appid=appid)
        res = await self._offload_call(self._reapply_tdp)
        # requested_w/applied_w reflect resulting sustained pl1 (readback), not the offsets
        return self._apply_result(res)

    async def set_tdp_boost_mode(self, mode: str, scope: str, appid=None) -> dict:
        """Set the boost behaviour (estable/auto/custom) for a scope and re-apply.
        Returns the full new state so the UI updates the segmented control + rails in
        ONE round-trip (the frontend does setTdp with it), avoiding a transient
        mode/rails mismatch."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is not None:  # invalid scope → no-op (never from the UI)
            self._clear_eco()
            self._tdp_profiles.set_boost_mode(resolved, mode, appid=appid)
            await self._offload_call(self._reapply_tdp)
        return self._tdp_state(await self._read_applied())

    def _preset_wclamp(self):
        lim = self._limits()
        return lim.min_w, lim.max_ac_w

    async def get_power_presets(self) -> dict:
        self._init()
        return self._power_presets.state()

    async def create_power_preset(self, watts: int, icon: str, boost=None, name="") -> dict:
        self._init()
        lo, hi = self._preset_wclamp()
        return self._power_presets.create(watts, icon, boost, name=name, min_w=lo, max_w=hi)

    async def update_power_preset(self, cid: str, watts: int, icon: str, boost=None, name="") -> dict:
        self._init()
        lo, hi = self._preset_wclamp()
        return self._power_presets.update(cid, watts, icon, boost, name=name, min_w=lo, max_w=hi)

    async def delete_power_preset(self, cid: str) -> dict:
        self._init()
        return self._power_presets.delete(cid)

    async def move_power_preset(self, cid: str, direction: int) -> dict:
        self._init()
        return self._power_presets.move(cid, direction)

    async def set_power_preset_hidden(self, cid: str, hidden: bool) -> dict:
        self._init()
        return self._power_presets.set_hidden(cid, bool(hidden))

    async def apply_power_preset(self, watts: int, scope: str, appid=None, boost=None) -> dict:
        """Apply a preset atomically: sustained watts (+ optional boost mode/offsets) in
        one re-apply. Mirrors set_tdp_watts' guards. boost=None leaves boost untouched."""
        self._init()
        if not self._tdp_control_on():
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": "tdp-control-disabled"}
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return {"requested_w": watts, "applied_w": None, "ok": False,
                    "detail": f"unknown scope: {scope}"}
        self._clear_eco()
        self._exit_firmware_mode()
        limits = self._limits()
        self._tdp_profiles.apply_preset(resolved, limits.clamp(watts, read_on_ac()), boost, appid=appid)
        res = await self._offload_call(self._reapply_tdp)
        return self._apply_result(res)

    async def create_game_profile(self, appid) -> None:
        self._init()
        self._tdp_profiles.create_game_from_global(appid)
        self._current_appid = str(appid)

    async def set_current_game(self, appid) -> dict:
        self._init()
        self._current_appid = str(appid) if appid is not None else None
        self._reset_auto_windows()  # don't let the previous game's signal gate the new one
        self._reapply_ticks = 0        # fresh ~30 min re-fit window for the new game
        self._adaptive_applied = False  # re-arm the mid-session adaptive drive for this game
        self._last_adaptive_points = None  # anti-churn baseline resets with the game
        # Auto-TDP no longer seeds PL1 from the learned band: the loop is band-decoupled
        # and explores to its own level. The learned band is a separate, explicit
        # suggestion (apply a fixed value) — see the UI. `_reapply_all` drives the
        # effective fan curve, including the adaptive learned curve when that mode is on.
        self._maybe_drive_adaptive_fan_curve()  # track + drive if adaptive with enough data
        self._reapply_all()
        # The TDP re-apply is off-loop; wait for it so the returned state's hardware
        # readback (applied_w) reflects the new game, not the previous setpoint.
        await self._drain_offloaded()
        return await self.get_tdp_state()

    def _restore_fans_safe(self) -> None:
        self._fan_max = False   # release the "a tope" override with the fans
        try:
            if getattr(self, "_fan_ctrl", None) is not None:
                self._fan_ctrl.restore_auto()
        except Exception:  # noqa: BLE001
            pass

    def _restore_color_safe(self) -> None:
        """Clear any applied color LUT (back to the panel's native look) so a
        disabled/uninstalled plugin leaves no lingering color. Guarded."""
        try:
            cb = getattr(self, "_color_backend", None)
            if cb is not None and cb.supported:
                cb.apply(dict(COLOR_NATIVE))
        except Exception:  # noqa: BLE001
            pass

    # ---- Sonido: audio EQ ---------------------------------------------------
    def _current_route(self) -> str:
        try:
            return self._audio.current_route()
        except Exception:  # noqa: BLE001
            return "speaker"

    def _effective_audio(self, route) -> dict:
        return self._audio_eq.effective(self._current_appid, route)

    def _reapply_audio(self) -> None:
        """Apply the effective EQ off the event loop (rewrites a conf + restarts the
        filter-chain service). Only offloads when the EQ is enabled — disabling tears the
        sink down explicitly, so a disabled EQ needs no work on resume/game change."""
        if self._audio_shutdown or not self._settings.get("audio_eq_enabled"):
            return
        self._offload(self._reapply_audio_sync)

    def _reapply_audio_sync(self) -> None:
        try:
            if not self._settings.get("audio_eq_enabled") or not self._audio.is_supported():
                return
            route = self._current_route()
            setting = self._effective_audio(route)
            gains, bass = self._guarded_gains(route, setting["gains"], setting["bass"])
            self._audio.set_gains(gains, bass, setting["loudness"], setting["balance"])
        except Exception as e:  # noqa: BLE001
            decky.logger.warning("audio EQ apply failed: %s", e)

    def _guarded_gains(self, route, gains, bass):
        if route == "speaker" and self._settings.get("speaker_guard_enabled", True):
            key = getattr(self._device, "key", None)
            gains = audio_safe.clamp_gains(gains, audio_safe.band_ceilings(key))
            bass = audio_safe.clamp_bass(bass, audio_safe.bass_ceiling(key))
        return gains, bass

    def _start_audio_loop(self) -> None:
        if self._audio_task is not None and not self._audio_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop in tests — skip task creation safely
        self._audio_task = asyncio.create_task(self._audio_loop())

    async def _stop_audio_loop(self) -> None:
        task = self._audio_task
        self._audio_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def _audio_check(self) -> dict:
        """Off-loop probe for the watcher: the active route + whether our EQ sink is still
        the default (WirePlumber can drop it on resume/hotplug)."""
        return {"route": self._current_route(), "is_default": self._audio.is_default()}

    async def _audio_loop(self) -> None:
        """While the EQ is enabled, keep it live with the QAM closed: re-apply when the
        output route changes (headphones ↔ speakers, each keeps its own curve) OR when our
        sink is no longer the default (WirePlumber re-picked the physical device on
        resume/hotplug → the effect silently dropped). Cheap: one off-loop probe every few
        seconds; _reapply_audio is diff-gated so a stable state does no audible work."""
        while True:
            try:
                await asyncio.sleep(_AUDIO_POLL_S)
                if not self._settings.get("audio_eq_enabled") or not self._audio.is_supported():
                    self._audio_route_last = None
                    continue
                probe = await self._offload_call(self._audio_check)
                if not probe["is_default"] or probe["route"] != self._audio_route_last:
                    self._audio_route_last = probe["route"]
                    self._reapply_audio()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                pass

    def _restore_audio_safe(self) -> None:
        """Remove the EQ sink and restore the previous default output so a
        disabled/uninstalled plugin leaves the audio untouched. Guarded."""
        try:
            if getattr(self, "_audio", None) is not None:
                self._audio.teardown()
        except Exception:  # noqa: BLE001
            pass

    def _audio_state(self) -> dict:
        route = self._current_route()
        eff = self._effective_audio(route)
        return {
            "supported": self._audio.is_supported(),
            "enabled": bool(self._settings.get("audio_eq_enabled", False)),
            "route": route,
            "appid": self._current_appid,
            "follows_global": self._audio_eq.is_following_global(self._current_appid),
            "has_game_profile": (self._current_appid is not None
                                 and self._audio_eq.has_game(self._current_appid)),
            "preset": eff["preset"],
            "gains": eff["gains"],
            "bass": eff["bass"],
            "loudness": eff["loudness"],
            "balance": eff["balance"],
            "test_playing": self._audio.is_test_playing(),
            "test_sample": self._test_sample if self._audio.is_test_playing() else None,
            "test_samples": audio_tone.sample_ids(),
            "presets": audio_presets.list_presets(getattr(self._device, "key", None)),
            "profiles": self._audio_profiles.list(),
            "device_name": self._device.display_name,
            "guard": bool(self._settings.get("speaker_guard_enabled", True)),
            "safe_limits": audio_safe.safe_limits(getattr(self._device, "key", None)),
        }

    async def get_audio_state(self) -> dict:
        self._init()
        return await self._offload_call(self._audio_state)

    async def set_audio_enabled(self, enabled: bool) -> dict:
        self._init()
        self._settings["audio_eq_enabled"] = bool(enabled)
        self._store.save(self._settings)
        if enabled:
            self._reapply_audio()
        else:
            self._offload(self._restore_audio_safe)
        return await self._offload_call(self._audio_state)

    async def set_speaker_guard(self, enabled: bool) -> dict:
        self._init()
        self._settings["speaker_guard_enabled"] = bool(enabled)
        self._store.save(self._settings)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def apply_audio_preset(self, preset: str, scope: str = "global", appid=None) -> dict:
        """Apply a preset to the active route for the given scope. device_tuned resolves
        to the per-machine speaker correction (flat on headphones)."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)  # pactl → off the loop
        setting = audio_presets.resolve_preset(getattr(self._device, "key", None), preset, route)
        self._audio_eq.set_setting(resolved, route, setting, appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def set_audio_band(self, index: int, gain: float, scope: str, appid=None) -> dict:
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)  # pactl → off the loop
        self._audio_eq.set_band(resolved, route, int(index), float(gain), appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def set_audio_bands(self, gains: list, scope: str, appid=None) -> dict:
        """Replace all 10 band gains for the active route (drag-commit of the whole curve)."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)  # pactl → off the loop
        self._audio_eq.set_bands(resolved, route, gains, appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def set_audio_loudness(self, on: bool, scope: str, appid=None) -> dict:
        """Toggle volume leveling (compression) for the active route — dialogue stays
        audible without loud peaks blasting; also protects small speakers."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)
        self._audio_eq.set_loudness(resolved, route, bool(on), appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def set_audio_balance(self, value: int, scope: str, appid=None) -> dict:
        """Set the L/R balance (-100..100) for the active route. Applies instantly — it
        only offsets the downstream pin, no filter-chain restart."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)
        self._audio_eq.set_balance(resolved, route, int(value), appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def save_audio_profile(self, name: str) -> dict:
        """Save the active route's current curve + bass as a named, reusable profile."""
        self._init()
        route = await self._offload_call(self._current_route)
        eff = self._effective_audio(route)
        self._audio_profiles.save(name, eff["gains"], eff["bass"])
        return await self._offload_call(self._audio_state)

    async def apply_audio_profile(self, name: str, scope: str, appid=None) -> dict:
        """Apply a saved profile's curve + bass to the active route for the given scope."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        prof = self._audio_profiles.get(name)
        if resolved is None or prof is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)
        self._audio_eq.set_bands(resolved, route, prof["gains"], appid=appid)
        self._audio_eq.set_bass(resolved, route, prof["bass"], appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def delete_audio_profile(self, name: str) -> dict:
        self._init()
        self._audio_profiles.delete(name)
        return await self._offload_call(self._audio_state)

    async def set_audio_test(self, playing: bool, sample: str = "full") -> dict:
        self._init()
        if playing:
            self._offload(lambda: self._start_audio_test_sync(sample))
        else:
            self._test_sample = None
            self._offload(self._audio.stop_test)
        return await self._offload_call(self._audio_state)

    def _start_audio_test_sync(self, sample: str) -> None:
        try:
            if sample not in audio_tone.sample_ids():
                sample = "full"
            name = f"pdc_test_{sample}_{audio_tone.CACHE_TAG}.wav"
            path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, name)
            if not os.path.exists(path):
                audio_tone.write_wav(path, audio_tone.render(sample))
            self._audio.start_test(path)
            self._test_sample = sample
        except Exception:  # noqa: BLE001
            self._test_sample = None

    async def set_audio_curve(self, gains: list, bass: int, scope: str, appid=None) -> dict:
        """Set the EQ gains and the bass-enhancement amount together in one apply (the tone
        sliders drive both — the Graves slider engages the bass enhancer)."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)  # pactl → off the loop
        self._audio_eq.set_bands(resolved, route, gains, appid=appid)
        self._audio_eq.set_bass(resolved, route, int(bass), appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def set_audio_follow_global(self, follow: bool, appid) -> dict:
        self._init()
        if appid is not None:
            appid = str(appid)
            if not follow and not self._audio_eq.has_game(appid):
                self._audio_eq.create_game_from_global(appid)
            self._audio_eq.set_follow_global(appid, bool(follow))
            self._current_appid = appid
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    async def reset_audio(self, scope: str = "global", appid=None) -> dict:
        """Flatten the active route's EQ for the given scope."""
        self._init()
        resolved = self._resolve_scope(scope, appid)
        if resolved is None:
            return await self._offload_call(self._audio_state)
        route = await self._offload_call(self._current_route)  # pactl → off the loop
        self._audio_eq.reset(resolved, route, appid=appid)
        self._reapply_audio()
        return await self._offload_call(self._audio_state)

    # ---- lifecycle ----------------------------------------------------------
    async def _main(self) -> None:
        self._init()
        # Single-worker executor for subprocess-backed applies (gamescopectl /
        # systemctl / ryzenadj) → keeps them off the event loop AND serialised.
        # Created here (not _init) so unit tests that never call _main run inline.
        self._apply_executor = ThreadPoolExecutor(max_workers=1)
        decky.logger.info(
            "Panel de Control v%s loaded (euid=%s)", read_version(), os.geteuid()
        )
        # Legion Go S hides its fan sensor unless lenovo_wmi_other is loaded with
        # expose_all_fans=Y — enable it (idempotent, no-op elsewhere, never raises).
        if fan_expose.ensure_fan_sensor():
            decky.logger.info("Legion fan sensor exposed (lenovo_wmi_other)")
        try:
            self._reapply_all()
            self._lifecycle.start()
            self._start_night_loop()
            # Re-assert the look across gamescope's session bringup, when a single apply
            # doesn't stick (see _await_display_backend). Always runs, not just cold boot.
            self._display_wait_task = asyncio.create_task(self._await_display_backend())
            # Auto-TDP is per-game: the loop always runs and each tick gates on the current
            # game's effective auto_tdp (holds when off), so it activates for a game that
            # has it on without waiting for the QAM.
            self._start_auto_loop()
            self._start_audio_loop()
            if self._learning_active():
                self._start_sampler()
        except Exception as e:  # noqa: BLE001
            decky.logger.error("TDP startup failed: %s", e)

    async def _unload(self) -> None:
        # Restore fans to firmware auto FIRST — before stopping other loops —
        # so the hardware is never left with a stale manual curve. The restores
        # spawn subprocesses (systemctl / gamescopectl) → run them off the loop and
        # await, then shut the executor down.
        await self._offload_call(self._restore_fans_safe)
        self._cancel_color_revert()
        wait_task = getattr(self, "_display_wait_task", None)
        if wait_task is not None:
            wait_task.cancel()
            self._display_wait_task = None
        self._stop_night_loop()
        await self._offload_call(self._restore_color_safe)
        self._audio_shutdown = True
        await self._stop_audio_loop()
        await self._offload_call(self._restore_audio_safe)
        await self._offload_call(self._restore_hhd_tdp)  # hand HHD's TDP back if we took it
        self._stop_auto_loop()
        if getattr(self, "_sampler", None) is not None:
            self._sampler.stop()
        if getattr(self, "_lifecycle", None) is not None:
            self._lifecycle.stop()
        self._shutdown_apply_executor()
        decky.logger.info("Panel de Control unloaded")

    def _shutdown_apply_executor(self) -> None:
        ex = getattr(self, "_apply_executor", None)
        if ex is not None:
            ex.shutdown(wait=False)
            self._apply_executor = None

    async def _uninstall(self) -> None:
        await self._offload_call(self._restore_fans_safe)
        await self._offload_call(self._restore_color_safe)
        self._audio_shutdown = True
        await self._stop_audio_loop()
        await self._offload_call(self._restore_audio_safe)
        await self._offload_call(self._restore_hhd_tdp)  # hand HHD's TDP back if we took it
        self._shutdown_apply_executor()
        fan_expose.remove_conf()  # drop the modprobe.d option we added (guarded)
        decky.logger.info("Panel de Control uninstalled")
